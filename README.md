# team_alerts

Small, transport-oriented library for **structured operational alerts**. The first supported channel is **Discord** (incoming webhooks); the layout leaves room for Slack, email, or ticket systems later without renaming the package.

Source repository: [github.com/dafoebriden/team_alerts](https://github.com/dafoebriden/team_alerts).

## Features

- **`Alert`** model with severity, optional title, exception, metadata, service, environment, and optional **`occurred_at`** (UTC instant for Discord timestamps)
- **Pure formatters** for Discord-safe text (truncation and splitting for long payloads), **`discord_relative_timestamp()`** for `<t:unix:R>` strings
- **`DiscordTransport`** using `requests` (`json=` for JSON posts; **multipart** when attaching tracebacks; optional **embeds** on the first post)
- **`DiscordTransportOptions`** — GitHub deep links, static URLs, env-sourced metadata, long tracebacks as **file uploads**, **embed mode** (`use_embeds`), **`allowed_mentions`** via **`AllowedMentionsOptions`**, and an **`alert_footer`** line on the **last** chunk when posts are split
- **`AlertClient`** with `send`, `low`, `high`, and `critical` helpers
- **`SendResult`** for simple success / HTTP / error reporting
- **`github_blob_url()`** for advanced callers building GitHub links outside the transport

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

### Embeds, timestamps, mentions, and last-chunk footers

```python
from datetime import datetime, timezone

from team_alerts import (
    Alert,
    AlertClient,
    AllowedMentionsOptions,
    DiscordTransport,
    DiscordTransportOptions,
    Severity,
)

opts = DiscordTransportOptions(
    use_embeds=True,
    embed_footer_text="billing-api",
    alert_footer="— end of alert —",  # last chunk only when split across posts
    allowed_mentions=AllowedMentionsOptions(
        role_ids=("987654321098765432",),  # explicit snowflakes only
    ),
)

transport = DiscordTransport("https://discord.com/api/webhooks/...", options=opts)
client = AlertClient(transport)

client.send(
    Alert(
        message="Disk usage above 90%",
        severity=Severity.HIGH,
        occurred_at=datetime.now(timezone.utc),
        metadata={"host": "db-1"},
    )
)
```

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
| `TEAM_ALERTS_USE_EMBEDS` | `1` / `true` / `yes` / `on` — send a rich embed (color by severity, fields, optional timestamp) |
| `TEAM_ALERTS_ALERT_FOOTER` | Plain-text footer appended to the **last** webhook when an alert is split across multiple posts |
| `TEAM_ALERTS_EMBED_FOOTER` | Optional short embed footer line (embed mode) |
| `TEAM_ALERTS_ALLOWED_ROLE_IDS` | Comma-separated role snowflakes for `allowed_mentions` |
| `TEAM_ALERTS_ALLOWED_USER_IDS` | Comma-separated user snowflakes for `allowed_mentions` |
| `TEAM_ALERTS_ALLOW_EVERYONE_MENTION` | Must be `1` / `true` to allow `@everyone` (off by default) |

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
- **Embeds** (`use_embeds=True`): severity maps to embed color; metadata becomes titled fields; ``Alert.occurred_at`` sets embed ``timestamp`` and a **When:** ``<t:unix:R>`` line in the description. Long message text beyond the embed description limit continues in plain ``content`` on follow-up webhooks.
- **``allowed_mentions``**: set ``DiscordTransportOptions.allowed_mentions`` to an ``AllowedMentionsOptions`` instance. Empty role/user lists with ``allow_everyone=False`` sends ``{"parse": []}`` so mentions are **not** parsed from free-form text; list explicit snowflakes to allow role/user pings. ``allow_everyone=True`` is opt-in for ``@everyone``.
- **``alert_footer``**: separate from the top banner; appended to the **last** chunk (plain mode) or the last continuation ``content`` post in embed mode.
- Missing or blank webhook URLs raise ``ConfigurationError`` at transport construction time.

### Ideas for later (not implemented)

- Richer embed layouts (author URL, images, multiple embeds per message).
- Optional ``allowed_mentions.parse`` for roles/users parsed from message text (high risk; off by default).

## Requirements

- Python 3.11+
- Runtime: `requests`
- Dev: `pytest` (via `pip install -e ".[dev]"`)
