# `changenotifier` configuration

The configuration file must exist at `/etc/changenotifier.conf` and be valid JSON. It requires two top-level keys and supports two optional ones.

### Required fields

| Field        | Type     | Description                                    |
|--------------|----------|------------------------------------------------|
| `webhook`    | string   | The HTTP URL that will receive POST notifications on every file change event. |
| `paths`      | array    | Either a list of strings (directory paths) or a list of dicts with per-path settings. See below for details. |

### Optional fields

| Field                | Type    | Default | Description                                                    |
|----------------------|---------|---------|----------------------------------------------------------------|
| `coalesce_timeout`   | number  | 15.0    | The grace period in seconds. Files changed within this window are grouped together; only the most recent file triggers a notification per watched path. Global default used when individual paths do not specify their own timeout. |
| `debug`              | boolean | false   | When true, log level is set to DEBUG immediately on startup. |

### Paths configuration

The `paths` array supports two syntaxes:

**Simple (global coalesce_timeout):**

```json
{
  "webhook": "https://example.com/webhook",
  "paths": [
    "/home/user/Music",
    "/home/user/Podcasts"
  ]
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

Paths that are dicts use the same keys as before: `path` specifies the directory to watch, and `coalesce_timeout` overrides the global value for that specific path.

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
