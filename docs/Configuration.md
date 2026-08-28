# `changenotifier` configuration

The configuration file is named `changenotifier.conf` and it must exist in one of the following paths:

* in any of the paths listed in `$XDG_CONFIG_DIRS`
* in `$XDG_CONFIG_HOME` (defaulting to `~/.config`)
* under `/etc`

The first file found wins.

## File format

The configuration file is JSON-formatted, and the minimum configuration requires a single key `paths`, but to be useful you will have to specify at least one optional key `command` or `webhook`, either at the top level, or in each path.

### Required fields

| Field     | Type    | Description                                    |
|-----------|---------|------------------------------------------------|
| `paths`   | array   | Either a list of directories to monitor or a list of dicts with per-path settings. See below for details. |

### Optional fields

| Field                | Type    | Default | Description                                                    |
|----------------------|---------|---------|----------------------------------------------------------------|
| `coalesce_timeout`   | number  | 15.0    | The grace period in seconds. Files changed within this window are grouped together; only the most recent file triggers a notification per watched path. Global default used when individual paths do not specify their own timeout. Also available per-path with dict syntax. |
| `webhook`            | string  |         | An optional HTTP URL that will receive POST notifications on every file change batch. Omit or set to null to prevent webhook notifications from being sent. An equivalent setting is available per-path, which overrides this global `webhook` setting. |
| `command`            | string  |         | An optional shell command to run on every file change batch. The following environment variables are available: `LATEST_MODIFIED_ITEM`, `LATEST_MODIFIED_FOLDER`, `LATEST_MODIFIED_FILE`, `EVENTS`, `SOURCE`. If the command fails, a warning is logged but the notification continues. An equivalent setting is available per-path, which overrides this global `command` setting |
| `debug`              | boolean | false   | When true, log level is set to `DEBUG` immediately on startup. |

### Paths configuration

The `paths` array supports two syntaxes:

**Simple (default `coalesce_timeout`):**

```json
{
  "webhook": "https://example.com/webhook",
  "paths": [
    "/home/user/Music",
    "/home/user/Podcasts"
  ]
}
```

Or using a command instead:

```json
{
  "paths": [
    "/home/user/Music"
  ],
  "command": "curl -X POST https://example.com/hook -d \"file=$LATEST_MODIFIED_ITEM\""
}
```

**Per-path with custom timeout:**

```json
{
  "webhook": "https://example.com/webhook",
  "paths": [
    "/home/user/Music",
    {
      "path": "/home/user/Desktop",
      "coalesce_timeout": 60.0
    }
  ]
}
```

**Per-path webhook override:**

```json
{
  "webhook": "https://example.com/global-webhook",
  "paths": [
    {
      "path": "/home/user/Music",
      "webhook": "https://hooks.example.com/music"
    },
    "/home/user/Podcasts"
  ]
}
```

The global webhook falls through to apply only to `/home/user/Podcasts`, which has no override.

**Per-path command override:**

```json
{
  "command": "curl -X POST https://example.com/global-hook -d \"file=$LATEST_MODIFIED_ITEM\"",
  "paths": [
    "/home/user/Music",
    {
      "path": "/home/user/Desktop",
      "command": "notify-send \"Desktop file changed: $LATEST_MODIFIED_FILE\""
    }
  ]
}
```

**Per-path webhook and command override:**

```json
{
  "webhook": "https://example.com/global-webhook",
  "command": "curl -X POST https://example.com/global-hook -d \"file=$LATEST_MODIFIED_ITEM\"",
  "paths": [
    "/home/user/Music",
    {
      "path": "/home/user/Desktop",
      "webhook": "https://hooks.example.com/desktop",
      "command": "notify-send \"Desktop file changed: $LATEST_MODIFIED_FILE\""
    }
  ]
}
```

**Partial override (inherit one, override the other):**

```json
{
  "webhook": "https://example.com/global-webhook",
  "paths": [
    "/home/user/Music",
    {
      "path": "/home/user/Desktop",
      "command": "notify-send \"Desktop file changed: $LATEST_MODIFIED_FILE\""
    }
  ]
}
```

This path overrides `command` but inherits the global `webhook`.

Paths that are dicts support the same keys as before (`path`, `coalesce_timeout`) plus the optional per-path overrides: `webhook` and `command`. Any key absent from a dict entry falls through to the global value.

### Fully commented example configuration

```jsonc
{
  // The URL that receives all webhook POST notifications when files change.
  "webhook": "https://hooks.example.com/changenotifier",

  // Optional: set to true to start with DEBUG-level logging (print event details).
  "debug": false,

  // Default grace period in seconds for all watch paths, used if individual paths
  // do not specify their own coalesce_timeout.
  "coalesce_timeout": 15.0,

  // Run this shell command on every file change event batch.
  "command": "curl -X POST https://example.com/hook -d \"file=$LATEST_MODIFIED_ITEM\"",

  // List of directories to watch. Each entry is one of:
  //   - A plain string: just a directory path (uses global coalesce_timeout).
  //   - A dict with:
  //       "path"          The directory to watch.
  //       "coalesce_timeout" The grace period in seconds for this path only
  //                          (overrides the global value if both are present).

  "paths": [

    // Plain string syntax - uses the global coalesce_timeout (15s above).
    "/home/user/Music",

    // Dict syntax with a custom timeout for this single directory.
    {
      "path": "/home/user/Desktop",
      "coalesce_timeout": 60.0
    },

    // Dict syntax without coalesce_timeout - falls back to the global value (15s above).
    {
      "path": "/home/user/Documents"
    }
  ]
}
```

In this example:
- The global coalesce timeout is 15 seconds, but `/home/user/Desktop` overrides it with a custom 60-second grace period.
- All detected changes in those directories trigger POST requests to the webhook URL with details about the most recently changed file per directory within each coalescing window — rather than notifying for every single change as it happens.
