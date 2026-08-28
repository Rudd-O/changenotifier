# `changenotifier`: have your computer perform actions when files change

This program monitors directories for file system changes and acts to notify you (via HTTP webhook notifications or command executions), when files are created, modified, moved, or deleted.

While it is mainly intended to be run as a simple service (e.g. with a service manager like `systemd`), you can run it interactively as well (e.g. under a `screen` session or a terminal window on your computer), or in a service orchestration platform (inside a pod of a Kubernetes cluster).

## How this program works

`changenotifier` recursively watches one or more directories you want to monitor on your Linux system, using the `inotifywait` utility.

When it detects file system events from a directory or its children, it begins to coalesce all events up to a configurable delay (defaulting to 15 seconds), then when no events taken place for that delay, runs the configured notification mechanisms (see below), with details about the latest changed file in the watched directory.

This program monitors for the inotify events `create, modify, close write, move to, move from, delete` but only emits events when files are done being modified (best-effort), deleted or moved into / out of the monitored directories.  The events listed in the notification correspond to the events that applied to the latest modified item in the batch of events that caused the notification; your notification mechanisms will not get a comprehensive listing of modifications.

### Shell command notifications

If configured to notify via command, the configured command run will have the following environment variables available:

* `LATEST_MODIFIED_ITEM`: full path to the latest item that was modified
* `EVENTS`: a list of inotify events (uppercase), separated by `|`

Command failures are logged as errors while the program moves on to continue business as usual.

The command will always be run before any configured webhook is called.

### Webhook notifications

If configured to notify via webhook, this program will send a JSON POST to the webhook URL:

```json
{
  "latest_modified_item": "/full/path/to/file",
  "latest_modified_folder": "/full/path/to",
  "latest_modified_file": "file",
  "events": "CLOSE_WRITE,ISDIR|CREATE",
  "source": "changenotifier"
}
```

Failed webhook deliveries (e.g. the server hosting the webhook is down, or it responds with a non-200 HTTP status, or it will not accept POST data) are retried every 30 seconds indefinitely until they are successful.

### Lifecycle mangement

`SIGTERM` triggers a clean shutdown (kills all watchers and coalescers, then exits).  `SIGUSR1` toggles log levels between DEBUG and INFO at runtime without restarting.

## Installation

### Prerequisites

- Linux
- The `inotifywait` command available (part of the `inotify-tools` package)
- Python 3.10 or later
- The `requests` Python package (listed as a dependency)

### Install from source

```bash
pip install .
```

Or install in development/editable mode:

```bash
pip install -e .
```

This registers the `changenotifier` CLI entry point, which invokes `main()` from `src/changenotifier/__init__.py`.

### RPM packaging

RPMs for Fedora are available at [repo.rudd-o.com](https://repo.rudd-o.com/).  The RPM specfile is included so you can build your own source tarball using `python3 -m build --sdist` and then build the RPM accordingly.

## Configuration

See the [configuration document](docs/Configuration.md) for details.
