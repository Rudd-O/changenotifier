#!/usr/bin/python3

import csv
import io
import json
import logging
import os
import queue
import shlex
import signal
import subprocess
import sys
import threading
import time
import traceback
import typing

import requests
import xdg.BaseDirectory

__QUIT: typing.Literal["QUIT"] = "QUIT"
__version__ = "0.1.0"


Param = typing.ParamSpec("Param")
RetType = typing.TypeVar("RetType")


def exitonerror(f: typing.Callable[Param, RetType]) -> typing.Callable[Param, RetType]:
    def inner(*a: Param.args, **kw: Param.kwargs) -> RetType:
        try:
            return f(*a, **kw)
        except BaseException as exc:
            traceback.print_exception(exc)
            os._exit(2)

    return inner


class Classifier(dict[str, dict[str, float]]):
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

    def latest_per_root(self) -> typing.Iterator[tuple[str, str, float]]:
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
        webhook: str | None,
        coalesce_timeout: float = 30,
        command: str | None = None,
    ):
        super().__init__()
        self.queue = queue
        self.root_times = Classifier(roots)
        self.webhook = webhook
        self.coalesce_timeout = coalesce_timeout
        self.command = command
        rooties = str(roots) if len(roots) > 1 else roots[0]
        self.logger = logging.getLogger("Coalescer").getChild(rooties)

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
        wh = "  Webhook enabled." if self.webhook else ""
        cm = "  Command execution enabled." if self.command else ""
        self.logger.info(
            f"Will notify {self.coalesce_timeout}s after changes stop.{wh}.{cm}"
        )
        evt_by_path: dict[str, str] = {}
        while True:
            if self.run_once(evt_by_path, self.queue) == "stop":
                break

    def notify(self, val: str, evt: str) -> None:
        self.logger.debug("EMIT: %s -- %s", val, evt)
        data = {
            "latest_modified_item": val,
            "latest_modified_folder": os.path.dirname(val),
            "latest_modified_file": os.path.basename(val),
            "events": evt,
            "source": "changenotifier",
        }

        if self.command is not None:
            env = os.environ | {k.upper(): v for k, v in data.items()}
            try:
                result = subprocess.run(self.command, shell=True, env=env, timeout=30)
                if result.returncode != 0:
                    self.logger.error("Command exited with code %d", result.returncode)
            except Exception as e:
                self.logger.warning("Command execution failed: %s", e)

        if self.webhook is not None:
            while True:
                try:
                    r = requests.post(self.webhook, json=data)
                    r.raise_for_status()
                    break
                except Exception as e:
                    print(
                        f"Failed webhook POST (retrying in 30 seconds): {e}",
                        file=sys.stderr,
                    )
                    time.sleep(30)

    def stop(self) -> None:
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
        self.notifier: subprocess.Popen[str] | None = None
        self.paths = paths
        self.logger = logging.getLogger("Watcher").getChild(
            str(paths) if len(paths) > 1 else paths[0]
        )

    @exitonerror
    def run(self) -> None:
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

    def stop(self) -> None:
        if self.notifier:
            self.notifier.kill()
            self.notifier = None
        self.join()


def toggle_log_level(*args: typing.Any) -> None:
    if logging.root.level == logging.DEBUG:
        logging.root.info("Changing log level to INFO")
        logging.root.setLevel(logging.INFO)
    else:
        logging.root.info("Changing log level to DEBUG")
        logging.root.setLevel(logging.DEBUG)


class _PathBase(typing.TypedDict):
    path: str


class PathWithTimeout(_PathBase, total=False):
    coalesce_timeout: float
    webhook: str | None
    command: str | None


def resolve_path_config(
    pth: str | PathWithTimeout,
    global_command: str | None,
    global_webhook: str | None,
    global_coalesce_timeout: float,
) -> tuple[str, str | None, str | None, float]:
    """Return (path, command, webhook, coalesce_timeout) for one entry."""
    if isinstance(pth, dict):
        path = pth["path"]
        timeout = pth.get("coalesce_timeout", global_coalesce_timeout)
        cmd = pth.get("command", global_command)
        whk = pth.get("webhook", global_webhook)
    else:
        path = pth
        timeout = global_coalesce_timeout
        cmd = global_command
        whk = global_webhook
    return path, cmd, whk, timeout


def main() -> None:
    cn = "changenotifier.conf"
    # Look for configs in ~/.config then in /etc.
    userconfigs = list(xdg.BaseDirectory.load_config_paths(cn)) or [
        os.path.join(xdg.BaseDirectory.xdg_config_home, cn)
    ]
    configfiles = userconfigs + [os.path.join("/etc", cn)]
    configfiles = [c for c in configfiles if os.path.exists(c)]
    assert configfiles, (
        f"The configuration file changenotifier.conf could not be found among {configfiles}"
    )
    if len(configfiles) > 1:
        print(
            f"Multiple configuration files found, picking {configfiles[0]}",
            file=sys.stderr,
        )

    with open(configfiles[0]) as conff:
        conf = json.load(conff)
        paths = typing.cast(typing.Iterable[str | PathWithTimeout], conf["paths"])
        webhook = typing.cast(str | None, conf.get("webhook"))
        debug = typing.cast(bool, conf.get("debug", False))
        command = typing.cast(str | None, conf.get("command"))
        coalesce_timeout = typing.cast(float, conf.get("coalesce_timeout", 15.0))

    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

    watchers: list[Watcher] = []
    coalescers: list[Coalescer] = []

    def stop(*args: typing.Any) -> None:
        print("Stopping notifier...", file=sys.stderr)
        for n in watchers:
            n.stop()
        print("Stopping coalescer...", file=sys.stderr)
        for c in coalescers:
            c.stop()
        sys.exit(0)

    for pth in paths:
        p, cmd, whk, t = resolve_path_config(pth, command, webhook, coalesce_timeout)
        q: queue.Queue[tuple[str, str] | typing.Literal["QUIT"]] = queue.Queue()
        c = Coalescer(q, [p], whk, t, cmd)
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
