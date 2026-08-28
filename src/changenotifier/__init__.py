#!/usr/bin/python3

import csv
import io
import json
import logging
import os
import queue
import requests
import shlex
import signal
import subprocess
import sys
import threading
import time
import traceback
import typing


Param = typing.ParamSpec("Param")
RetType = typing.TypeVar("RetType")
__QUIT: typing.Literal["QUIT"] = "QUIT"
__version__ = "0.0.1"


def exitonerror(f: typing.Callable[Param, RetType]) -> typing.Callable[Param, RetType]:
    def inner(*a: Param.args, **kw: Param.kwargs):
        try:
            return f(*a, **kw)
        except BaseException as exc:
            traceback.print_exception(exc)
            os._exit(2)

    return inner


class Classifier(dict[str, dict[str, typing.Any]]):
    def __init__(self, roots: list[str]):
        for root in roots:
            self[os.path.abspath(root)] = {}

    def record_time(self, path: str) -> bool:
        abspath = os.path.abspath(path)
        now = time.time()
        matched = False
        for root in self:
            if not os.path.relpath(abspath, root).startswith(os.path.pardir):
                matched = True
                self[root][path] = now
                break
        return matched

    def latest_per_root(self):
        for root, data in self.items():
            if not data:
                continue
            path, t = sorted(data.items(), key=lambda k: k[1])[-1]
            yield root, path, t

    def clear_key(self, root: str) -> None:
        self[root] = {}


class Coalescer(threading.Thread):
    def __init__(
        self,
        queue: queue.Queue[tuple[str, str] | typing.Literal["QUIT"]],
        roots: list[str],
        webhook: str,
        coalesce_timeout: float = 30,
    ):
        super().__init__()
        self.queue = queue
        self.root_times = Classifier(roots)
        self.webhook = webhook
        self.coalesce_timeout = coalesce_timeout
        self.logger = logging.getLogger("Coalescer").getChild(
            str(roots) if len(roots) > 1 else roots[0]
        )

    def run_once(
        self,
        evt_by_path: dict[str, str],
        q: queue.Queue[tuple[str, str] | typing.Literal["QUIT"]],
    ) -> typing.Literal["continue"] | typing.Literal["stop"]:
        debug = self.logger.debug
        b4get = time.time()
        oldest = [
            self.coalesce_timeout - (b4get - t)
            for _, _, t in self.root_times.latest_per_root()
        ]
        timeout = min([self.coalesce_timeout] + oldest) if oldest else None
        if timeout is None:
            debug("Waiting indefinitely")
        else:
            if timeout < 0.0:
                timeout = 0.0
            debug("Waiting for %.1f seconds", timeout)

        try:
            qitem = q.get(timeout=timeout)
            if qitem == __QUIT:
                return "stop"
            val, evt = qitem
            evt_by_path[val] = evt
            if self.root_times.record_time(val):
                return "continue"
        except queue.Empty:
            pass

        afterget = time.time()
        notified = False
        for root, path, t in self.root_times.latest_per_root():
            ago = afterget - t
            if ago >= self.coalesce_timeout:
                self.notify(path, evt_by_path[path])
                self.root_times.clear_key(root)
                notified = True
        if notified:
            evt_by_path.clear()

        return "continue"

    @exitonerror
    def run(self) -> None:
        evt_by_path: dict[str, str] = {}
        while True:
            if self.run_once(evt_by_path, self.queue) == "stop":
                break

    def notify(self, val: str, evt: str):
        self.logger.debug("EMIT: %s -- %s", val, evt)
        data = {
            "latest_modified_item": val,
            "latest_modified_folder": os.path.dirname(val),
            "latest_modified_file": os.path.basename(val),
            "events": evt,
            "source": "changenotifier",
        }
        while True:
            try:
                r = requests.post(webhook, json=data)
                r.raise_for_status()
                break
            except Exception as e:
                print(
                    f"Failed webhook POST (retrying in 30 seconds): {e}",
                    file=sys.stderr,
                )
                time.sleep(30)

    def stop(self):
        self.queue.put(__QUIT)
        self.join()


class Watcher(threading.Thread):
    def __init__(
        self,
        queue: queue.Queue[tuple[str, str] | typing.Literal["QUIT"]],
        paths: list[str],
    ):
        super().__init__()
        self.queue = queue
        self.notifier = None
        self.paths = paths
        self.logger = logging.getLogger("Watcher").getChild(
            str(paths) if len(paths) > 1 else paths[0]
        )

    @exitonerror
    def run(self):
        q = self.queue
        debug = self.logger.debug
        modified = {}
        with open(os.devnull, "rb") as null:
            paths = " ".join(shlex.quote(p) for p in self.paths)
            self.notifier = notifier = subprocess.Popen(
                f"inotifywait --csv -e open,modify,close_write,moved_to,moved_from,delete -r -m {paths}",
                shell=True,
                stdin=null,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            )
            assert notifier.stdout is not None

        while True:
            line = notifier.stdout.readline()
            if not line:
                break
            r = csv.reader(io.StringIO(line), delimiter=",", quotechar='"')
            for dir_, events, fname in r:
                dir_ = dir_.rstrip("/")
                if not dir_:
                    dir_ = "/"
                if "DELETE" in events or "MOVED" in events:
                    x = dir_ if not fname else os.path.join(dir_, fname)
                    debug("%s: %s", events, x)
                    q.put((x, events))
                elif "MODIFY" in events or "CREATE" in events:
                    debug("%s: %s", events, os.path.join(dir_, fname))
                    modified[os.path.join(dir_, fname)] = True
                elif "CLOSE_WRITE" in events:
                    debug("%s: %s", events, os.path.join(dir_, fname))
                    if os.path.join(dir_, fname) in modified:
                        debug("...was a match")
                        del modified[os.path.join(dir_, fname)]
                        q.put((os.path.join(dir_, fname), events))
                    else:
                        debug("...was not a match")
                else:
                    x = dir_ if not fname else os.path.join(dir_, fname)
                    debug("Ignoring: %s for %s", events, x)

        notifier.wait()

    def stop(self):
        if self.notifier:
            self.notifier.kill()
            self.notifier = None
        self.join()


def toggle_log_level(*args: typing.Any):
    if logging.root.level == logging.DEBUG:
        logging.root.info("Changing log level to INFO")
        logging.root.setLevel(logging.INFO)
    else:
        logging.root.info("Changing log level to DEBUG")
        logging.root.setLevel(logging.DEBUG)


class PathWithTimeout(typing.TypedDict):
    path: str
    coalesce_timeout: float


with open("/etc/changenotifier.conf") as conff:
    conf = json.load(conff)
    paths = typing.cast(typing.Iterable[str | PathWithTimeout], conf["paths"])
    webhook = typing.cast(str, conf["webhook"])
    debug = typing.cast(bool, conf.get("debug", False))
    coalesce_timeout = typing.cast(float, conf.get("coalesce_timeout", 15.0))

logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

watchers: list[Watcher] = []
coalescers: list[Coalescer] = []


def stop(*args: typing.Any):
    print("Stopping notifier...", file=sys.stderr)
    [n.stop() for n in watchers]
    print("Stopping coalescer...", file=sys.stderr)
    [c.stop() for c in coalescers]
    sys.exit(0)


for pth in paths:
    if isinstance(pth, dict):
        p: str = pth["path"]
        t: float = pth["coalesce_timeout"]
    else:
        p = pth
        t = coalesce_timeout
    q: queue.Queue[tuple[str, str] | typing.Literal["QUIT"]] = queue.Queue()
    c = Coalescer(q, [p], webhook, t)
    n = Watcher(q, [p])
    c.start()
    n.start()

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGUSR1, toggle_log_level)

try:
    for n in watchers:
        n.join()
except KeyboardInterrupt:
    stop()
