import typing

from changenotifier import resolve_path_config


def make_fake_config(  # noqa: INP001
    paths_entry: list[typing.Any],
    webhook: str | None = None,
    command: str | None = None,
    coalesce_timeout: float | None = None,
) -> dict[str, typing.Any]:
    conf: dict[str, typing.Any] = {"paths": paths_entry}
    if webhook is not None:
        conf["webhook"] = webhook
    if command is not None:
        conf["command"] = command
    if coalesce_timeout is not None:
        conf["coalesce_timeout"] = coalesce_timeout
    return conf


# ---------------------------------------------------------------------------
# per-path webhook override tests
# ---------------------------------------------------------------------------


class TestPerPathWebhookOverride:
    def test_dict_path_webhook_overrides_global(self) -> None:
        global_whk = "https://example.com/global-webhook"
        result = resolve_path_config(
            {"path": "/home/user/Music", "webhook": "https://hooks.example.com/music"},
            global_command=None,
            global_webhook=global_whk,
            global_coalesce_timeout=15.0,
        )
        p, _, whk, _ = result
        assert p == "/home/user/Music"
        assert whk == "https://hooks.example.com/music", whk

    def test_string_path_uses_global_webhook(self) -> None:
        global_whk = "https://example.com/global-webhook"
        result = resolve_path_config(
            "/home/user/Music",
            global_command=None,
            global_webhook=global_whk,
            global_coalesce_timeout=15.0,
        )
        p, _, whk, _ = result
        assert p == "/home/user/Music"
        assert whk == global_whk

    def test_per_path_webhook_none_overrides_global(self) -> None:
        global_whk = "https://example.com/global-webhook"
        result = resolve_path_config(
            {"path": "/home/user/Music", "webhook": None},
            global_command=None,
            global_webhook=global_whk,
            global_coalesce_timeout=15.0,
        )
        _, _, whk, _ = result
        assert whk is None


# ---------------------------------------------------------------------------
# per-path command override tests
# ---------------------------------------------------------------------------


class TestPerPathCommandOverride:
    def test_dict_path_command_overrides_global(self) -> None:
        global_cmd = "curl -s https://example.com/global-hook"
        result = resolve_path_config(
            {
                "path": "/home/user/Desktop",
                "command": "npx notify-send 'Desktop change'",
            },
            global_command=global_cmd,
            global_webhook=None,
            global_coalesce_timeout=15.0,
        )
        _, cmd, _, _ = result  # noqa: PT018
        assert cmd == "npx notify-send 'Desktop change'"

    def test_string_path_uses_global_command(self) -> None:
        global_cmd = "curl -s https://example.com/global-hook"
        result = resolve_path_config(
            "/home/user/Music",
            global_command=global_cmd,
            global_webhook=None,
            global_coalesce_timeout=15.0,
        )
        _, cmd, _, _ = result
        assert cmd == global_cmd

    def test_per_path_command_none_overrides_global(self) -> None:
        global_cmd = "curl -s https://example.com/global-hook"
        result = resolve_path_config(
            {
                "path": "/home/user/Desktop",
                "command": None,
            },
            global_command=global_cmd,
            global_webhook=None,
            global_coalesce_timeout=15.0,
        )
        _, cmd, _, _ = result
        assert cmd is None


# ---------------------------------------------------------------------------
# partial override tests (inherit one, override the other)
# ---------------------------------------------------------------------------


class TestPartialOverride:
    def test_per_path_webhook_only_inherits_global_command(self) -> None:
        global_whk = "https://example.com/global-webhook"
        global_cmd = "curl -s https://example.com/global-hook"
        result = resolve_path_config(
            {
                "path": "/home/user/Desktop",
                "webhook": "https://hooks.example.com/desktop",
            },
            global_command=global_cmd,
            global_webhook=global_whk,
            global_coalesce_timeout=15.0,
        )
        _, cmd, whk, _ = result
        assert whk == "https://hooks.example.com/desktop"
        assert cmd == global_cmd

    def test_per_path_command_only_inherits_global_webhook(self) -> None:
        global_whk = "https://example.com/global-webhook"
        global_cmd = "curl -s https://example.com/global-hook"
        result = resolve_path_config(
            {
                "path": "/home/user/Desktop",
                "command": "npx notify-send 'Desktop change'",
            },
            global_command=global_cmd,
            global_webhook=global_whk,
            global_coalesce_timeout=15.0,
        )
        _, cmd, whk, _ = result
        assert cmd == "npx notify-send 'Desktop change'"
        assert whk == global_whk

    def test_both_override(self) -> None:
        global_whk = "https://example.com/global-webhook"
        global_cmd = "curl -s https://example.com/global-hook"
        result = resolve_path_config(
            {
                "path": "/home/user/Desktop",
                "webhook": "https://hooks.example.com/desktop",
                "command": "npx notify-send 'Desktop change'",
            },
            global_command=global_cmd,
            global_webhook=global_whk,
            global_coalesce_timeout=15.0,
        )
        _, cmd, whk, _ = result
        assert whk == "https://hooks.example.com/desktop"
        assert cmd == "npx notify-send 'Desktop change'"


# ---------------------------------------------------------------------------
# coalesce_timeout still works alongside webhook/command overrides
# ---------------------------------------------------------------------------


class TestCoalesceTimeoutWithOverrides:
    def test_dict_path_all_keys_override(self) -> None:
        global_whk = "https://example.com/global-webhook"
        global_cmd = "curl -s https://example.com/global-hook"
        result = resolve_path_config(
            {
                "path": "/home/user/Desktop",
                "coalesce_timeout": 60.0,
                "webhook": "https://hooks.example.com/desktop",
                "command": "npx notify-send 'Desktop change'",
            },
            global_command=global_cmd,
            global_webhook=global_whk,
            global_coalesce_timeout=15.0,
        )
        p, cmd, whk, t = result
        assert p == "/home/user/Desktop"
        assert whk == "https://hooks.example.com/desktop"
        assert cmd == "npx notify-send 'Desktop change'"
        assert t == 60.0

    def test_dict_path_no_coalesce_timeout_inherits_global(self) -> None:
        global_whk = "https://example.com/global-webhook"
        result = resolve_path_config(
            {
                "path": "/home/user/Desktop",
                "webhook": "https://hooks.example.com/desktop",
            },
            global_command=None,
            global_webhook=global_whk,
            global_coalesce_timeout=15.0,
        )
        _, _, whk, t = result
        assert whk == "https://hooks.example.com/desktop"
        assert t == 15.0

    def test_string_path_uses_all_globals(self) -> None:
        global_whk = "https://example.com/global-webhook"
        global_cmd = "curl -s https://example.com/global-hook"
        result = resolve_path_config(
            "/home/user/Music",
            global_command=global_cmd,
            global_webhook=global_whk,
            global_coalesce_timeout=15.0,
        )
        p, cmd, whk, t = result
        assert p == "/home/user/Music"
        assert cmd == global_cmd
        assert whk == global_whk
        assert t == 15.0
