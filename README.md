# team_alerts

Small, transport-oriented library for **structured operational alerts**. The first supported channel is **Discord** (incoming webhooks); the layout leaves room for Slack, email, or ticket systems later without renaming the package.

## Features

- **`Alert`** model with severity, optional title, exception, metadata, service, and environment fields
- **Pure formatters** for Discord-safe text (truncation and splitting for long payloads)
- **`DiscordTransport`** using `requests` (`json=` for JSON posts; **multipart** when attaching tracebacks)
- **`DiscordTransportOptions`** — optional GitHub deep links, static URLs, env-sourced metadata, and **file uploads** for long tracebacks
- **`AlertClient`** with `send`, `low`, `high`, and `critical` helpers
- **`SendResult`** for simple success / HTTP / error reporting

## Install

From this directory (editable install while you develop):

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

## Quickstart

```python
from team_alerts import Alert, AlertClient, DiscordTransport, Severity

transport = DiscordTransport("https://discord.com/api/webhooks/...")
client = AlertClient(transport)

client.high("Disk usage above 90%", service="billing-api", environment="prod")

client.send(
    Alert(
        message="Manual alert",
        severity=Severity.CRITICAL,
        title="Deploy failed",
        metadata={"commit": "abc123"},
    )
)
```

### Optional Discord behavior (GitHub links + long tracebacks as files)

```python
from team_alerts import (
    AlertClient,
    DiscordTransport,
    DiscordTransportOptions,
    GitHubLinkOptions,
)

opts = DiscordTransportOptions(
    metadata_url_link_style="markdown",  # ``[CI](url)`` instead of ``<url>``
    alert_banner="━━━ staging ━━━",  # or ``""`` to turn off; default is a box line at the **top**
    attach_exception_over_chars=1600,
    github=GitHubLinkOptions(
        repository="myorg/myrepo",
        ref="abc123def",
        source_root="/abs/path/to/repo",  # needed to map traceback paths → GitHub paths
    ),
    static_links={"CI": "https://github.com/myorg/myrepo/actions/runs/1"},
    env_metadata_keys=("GITHUB_RUN_ID",),
)

transport = DiscordTransport("https://discord.com/api/webhooks/...", options=opts)
client = AlertClient(transport)
```

When `attach_exception_over_chars` is set and the formatted traceback is longer, the **first** webhook call sends **multipart** data: a short `content` plus `traceback.txt` (remaining message chunks, if any, are plain JSON posts).

GitHub URLs are merged into alert metadata (shown in the Discord body) **only** when `source_root` is set so traceback file paths can be relativized into the repo.

### Environment-based client

```python
from team_alerts import AlertClient, DiscordTransportOptions

# Optional: load TEAM_ALERTS_* / GITHUB_* driven options from the environment
client = AlertClient.from_discord_webhook_env(
    discord_options=DiscordTransportOptions.from_env(),
)
client.low("Hello from env-configured webhook")
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `DISCORD_WEBHOOK` | Incoming webhook URL used by `AlertClient.from_discord_webhook_env()` |
| `RUN_LIVE_DISCORD_TESTS` | Set to `1` to enable real webhook tests in `tests/test_live_discord.py` |
| `GITHUB_REPOSITORY` | `owner/repo`; used with `DiscordTransportOptions.from_env()` |
| `GITHUB_SHA`, `GIT_COMMIT`, `GITHUB_REF_NAME` | Ref for GitHub blob links (`from_env()` picks the first that is set) |
| `GITHUB_SERVER_URL` | GitHub Enterprise / API base; `from_env()` maps `/api/v3` hosts to a web base when possible |
| `TEAM_ALERTS_GITHUB_SOURCE_ROOT` | Absolute repo root on disk for traceback → repo-relative paths |
| `TEAM_ALERTS_ATTACH_EXCEPTION_OVER` | Integer: send traceback as a **file** when longer than this many characters |
| `TEAM_ALERTS_ENV_METADATA` | Comma-separated env var **names** to copy into alert metadata when present |
| `TEAM_ALERTS_METADATA_URL_STYLE` | `markdown` (or `md` / `labeled`) for `[key](url)` metadata links; omit or any other value for `<url>` |
| `TEAM_ALERTS_ALERT_BANNER` | `0` / `false` / `off` disables the top separator; any other non-empty string is a **custom** banner line (omit for the built-in default) |

### `.env.local` for pytest

If you create a **`.env.local`** file at the project root (same directory as `pyproject.toml`), pytest loads it automatically before tests run. Use the usual `KEY=value` or `export KEY=value` lines; values can be single- or double-quoted.

Variables already set in your shell take precedence (`setdefault`), so you can override file values when needed.

`.env.local` is listed in `.gitignore` so it is not committed.

## Running tests

```bash
source .venv/bin/activate
pytest
```

Unit tests mock HTTP; no Discord account is required for the default run.

## Live Discord tests

Point `DISCORD_WEBHOOK` at a channel webhook and enable the live suite:

```bash
export DISCORD_WEBHOOK='https://discord.com/api/webhooks/...'
export RUN_LIVE_DISCORD_TESTS=1
pytest tests/test_live_discord.py -v
```

## Design notes

- Formatting lives in `team_alerts.formatters`; transports stay focused on HTTP and optional enrichment.
- Metadata values that look like a single `http(s)` URL are sent as **clickable** links: default ``<url>`` (no preview), or ``[metadata_key](url)`` when ``DiscordTransportOptions.metadata_url_link_style="markdown"`` (closing ``)`` in URLs is percent-escaped for Discord markdown).
- Each Discord post from ``DiscordTransport`` starts with a **banner line** (see ``DEFAULT_ALERT_BANNER_LINE`` in ``constants``) so consecutive alerts are easier to scan; only the **first** chunk includes it when a message is split (one newline after the banner, no extra blank line). Disable with ``alert_banner=""``.

### Ideas for later (not implemented)

- **Embeds** for color-by-severity and titled fields (richer, more moving parts).
- **Timestamps** (Discord ``<t:unix:R>``) in metadata when you pass a UTC instant.
- **Role / user pings** via ``allowed_mentions`` (needs explicit, careful wiring so you do not ping everyone by accident).
- **Extra footers** (separate from the default top banner line) for long multi-post alerts.
- `DiscordTransport` splits oversized **message** content across multiple webhook posts; long **exceptions** can optionally go out as an attachment on the first post.
- Missing or blank webhook URLs raise `ConfigurationError` at construction time.
- `github_blob_url()` is exposed for advanced callers who build links themselves.

## Requirements

- Python 3.11+
- Runtime: `requests`
- Dev: `pytest` (via `pip install -e ".[dev]"`)
