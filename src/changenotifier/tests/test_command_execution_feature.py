import os
import queue
import subprocess as _subprocess
import typing
from unittest import mock

import pytest

from changenotifier import Coalescer

_Q = queue.Queue[tuple[str, str] | typing.Literal["QUIT"]]


def make_coalescer(
    webhook: str | None = "http://localhost/webhook",
    command: str | None = None,
) -> Coalescer:
    paths = ["/tmp/placeholder"]
    q: _Q = queue.Queue()
    return Coalescer(q, paths, webhook, command=command)


# ---------------------------------------------------------------------------
# data payload (unchanged by webhook becoming optional)
# ---------------------------------------------------------------------------


class TestDataPayload:
    def test_notify_payload_has_all_fields(self) -> None:
        with mock.patch("requests.post") as post_mock:
            resp = mock.Mock()
            resp.raise_for_status.return_value = None
            post_mock.return_value = resp

            c = make_coalescer(command=None)
            c.notify("/a/b/c.txt", "MODIFY|CLOSE_WRITE")

        data = post_mock.call_args[1]["json"]
        assert data == {
            "latest_modified_item": "/a/b/c.txt",
            "latest_modified_folder": "/a/b",
            "latest_modified_file": "c.txt",
            "events": "MODIFY|CLOSE_WRITE",
            "source": "changenotifier",
        }

    def test_folder_is_parent_dir(self) -> None:
        with mock.patch("requests.post") as post_mock:
            resp = mock.Mock()
            resp.raise_for_status.return_value = None
            post_mock.return_value = resp

            c = make_coalescer(command=None)
            c.notify("/tmp/hello.txt", "CREATE")

        assert post_mock.call_args[1]["json"]["latest_modified_folder"] == "/tmp"


# ---------------------------------------------------------------------------
# neither webhook nor command  (no external I/O should happen)
# ---------------------------------------------------------------------------


class TestNoWebhookNoCommand:
    def test_does_nothing_external(self) -> None:
        with mock.patch("requests.post") as post_mock:
            c = make_coalescer(webhook=None, command=None)
            c.notify("/tmp/x.txt", "CREATE")

        post_mock.assert_not_called()

    def test_subprocess_not_invoked(self) -> None:
        subprocess_called = False

        def raise_on_sp(
            *_a: object, **_kw: object
        ) -> _subprocess.CompletedProcess[str]:
            nonlocal subprocess_called
            subprocess_called = True
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=raise_on_sp):
            c = make_coalescer(webhook=None, command=None)
            c.notify("/tmp/x.txt", "CREATE")

        assert not subprocess_called


# ---------------------------------------------------------------------------
# webhook only  (no command execution)
# ---------------------------------------------------------------------------


class TestWebhookOnly:
    def test_webhook_sent(self) -> None:
        with mock.patch("requests.post") as post_mock:
            resp = mock.Mock()
            resp.raise_for_status.return_value = None
            post_mock.return_value = resp

            c = make_coalescer(webhook="http://localhost/webhook", command=None)
            c.notify("/tmp/x.txt", "CREATE")

        assert post_mock.call_count == 1

    def test_subprocess_not_invoked(self) -> None:
        subprocess_called = False

        def raise_on_sp(
            *_a: object, **_kw: object
        ) -> _subprocess.CompletedProcess[str]:
            nonlocal subprocess_called
            subprocess_called = True
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=raise_on_sp):
            with mock.patch("requests.post") as post_mock:
                resp = mock.Mock()
                resp.raise_for_status.return_value = None
                post_mock.return_value = resp

                c = make_coalescer(webhook="http://localhost/webhook", command=None)
                c.notify("/tmp/x.txt", "CREATE")

        assert not subprocess_called


# ---------------------------------------------------------------------------
# command only  (no webhook)
# ---------------------------------------------------------------------------


class TestCommandOnly:
    def test_command_executed(self) -> None:
        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(returncode=0)

            c = make_coalescer(webhook=None, command="echo hello")
            c.notify("/tmp/x.txt", "CREATE")

        run_mock.assert_called_once_with(
            "echo hello", shell=True, env=mock.ANY, timeout=30
        )

    def test_env_contains_notification_data(self) -> None:
        path = "/home/user/Music/song.mp3"
        events = "CLOSE_WRITE|CREATE"
        env_snapshot: dict[str, str] = {}

        def capture(
            cmd: object,
            shell: bool = False,
            env: dict[str, str] | None = None,
            timeout: int = 30,
        ) -> mock.Mock:
            env_snapshot.update(env or {})
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=capture):
            c = make_coalescer(webhook=None, command="cmd")
            c.notify(path, events)

        assert env_snapshot["LATEST_MODIFIED_ITEM"] == path
        assert env_snapshot["LATEST_MODIFIED_FOLDER"] == os.path.dirname(path)
        assert env_snapshot["LATEST_MODIFIED_FILE"] == os.path.basename(path)
        assert env_snapshot["EVENTS"] == events
        assert env_snapshot["SOURCE"] == "changenotifier"

    def test_command_failure_does_not_crash_notify(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=1)):
            c = make_coalescer(webhook=None, command="false")
            c.notify("/tmp/x.txt", "CREATE")

        assert "Command exited with code 1" in caplog.text


# ---------------------------------------------------------------------------
# both webhook and command
# ---------------------------------------------------------------------------


class TestWebhookAndCommand:
    def test_command_runs_before_webhook(self) -> None:
        order: list[str] = []

        def on_cmd(
            cmd: object,
            shell: bool = False,
            env: dict[str, str] | None = None,
            timeout: int = 30,
        ) -> mock.Mock:
            order.append("cmd")
            return mock.Mock(returncode=0)

        def on_req(url: str, json: dict[str, object] | None = None) -> mock.Mock:
            order.append("webhook")
            resp = mock.Mock()
            resp.raise_for_status.return_value = None
            resp.status_code = 200
            return resp

        with mock.patch("subprocess.run", side_effect=on_cmd):
            with mock.patch("requests.post", side_effect=on_req):
                c = make_coalescer(
                    webhook="http://localhost/webhook", command="echo ok"
                )
                c.notify("/tmp/x.txt", "CREATE")

        assert order == ["cmd", "webhook"]
