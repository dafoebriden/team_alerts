# team_alerts

Small, transport-oriented library for **structured operational alerts**. The first supported channel is **Discord** (incoming webhooks); the layout leaves room for Slack, email, or ticket systems later without renaming the package.

Source repository: [github.com/dafoebriden/team_alerts](https://github.com/dafoebriden/team_alerts).

## Features

- **`Alert`** model with severity, optional title, exception, metadata, service, environment, optional **`occurred_at`** (UTC instant for Discord timestamps), optional **`correlation_id`**, **`run_id`**, **`dedupe_key`**, and per-send **`discord_payload_style`** (`"auto"` / `"embed"` / `"plain"`) to override Discord layout
- **Pure formatters** for Discord-safe text (truncation and splitting for long payloads), **`discord_relative_timestamp()`** for `<t:unix:R>` strings
- **`DiscordTransport`** using `requests` (`json=` for JSON posts; **multipart** when attaching tracebacks); **rich embeds are the default** (`DiscordTransportOptions.use_embeds` defaults to `true`); configurable **retries with backoff** for transient HTTP failures and **429** (`Retry-After`), applied **per webhook POST** (see [Delivery semantics](#delivery-semantics))
- **`DiscordTransportOptions`** — pass as ``options`` and/or keywords on **`DiscordTransport`**: :meth:`from_env` is the baseline; non-default fields on ``options`` and then kwargs override; anything you leave at library defaults on ``options`` keeps the env value
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

Force a **single** alert back to classic plain text (no embed) while keeping embeds as the transport default:

```python
client.send(
    Alert(
        message="Plain-only for this message",
        severity=Severity.HIGH,
        discord_payload_style="plain",
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

You can also pass option fields as keywords (merged into ``options`` or into empty defaults):

```python
transport = DiscordTransport(
    "https://discord.com/api/webhooks/...",
    use_embeds=False,
    webhook_max_attempts=5,
)
```

Baseline is :meth:`DiscordTransportOptions.from_env`. Override with any ``options`` fields that differ from library defaults, then with **keyword arguments** (kwargs always win). Fields still at defaults on ``options`` behave as “unset” and keep the env value.

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
    embed_footer_text="billing-api",
    embed_footer_append_service_env=True,
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

``AlertClient.from_discord_webhook_env`` reads the webhook URL from ``DISCORD_WEBHOOK`` (or another variable you name), then uses the same merge as :class:`DiscordTransport` (``from_env`` baseline, ``discord_options``, kwargs).

```python
from team_alerts import AlertClient, DiscordTransportOptions

# No explicit options: same as empty config, env supplies TEAM_ALERTS_* / GITHUB_* where set
client = AlertClient.from_discord_webhook_env()
client.low("Hello")

# Partial config: e.g. force plain mode in code; GitHub/ref etc. can still come from env
client = AlertClient.from_discord_webhook_env(
    discord_options=DiscordTransportOptions(use_embeds=False),
)

# Same via kwargs (merged with discord_options if both are passed)
client = AlertClient.from_discord_webhook_env(use_embeds=False, webhook_max_attempts=1)
```

Use :meth:`DiscordTransportOptions.from_env` when you need the **environment-only** snapshot (tests, building another layer on top).

## Environment variables

| Variable | Purpose |
|----------|---------|
| `DISCORD_WEBHOOK` | Incoming webhook URL used by `AlertClient.from_discord_webhook_env()` |
| `RUN_LIVE_DISCORD_TESTS` | Set to `1` to enable real webhook tests in `tests/test_live_discord.py` |
| `GITHUB_REPOSITORY` | `owner/repo` for GitHub blob links (via `from_env()` / transport merge) |
| `GITHUB_SHA`, `GIT_COMMIT`, `GITHUB_REF_NAME` | Ref for GitHub blob links (first set wins in `from_env()`) |
| `GITHUB_SERVER_URL` | GitHub Enterprise / API base; `from_env()` maps `/api/v3` hosts to a web base when possible |
| `TEAM_ALERTS_GITHUB_SOURCE_ROOT` | Absolute repo root on disk for traceback → repo-relative paths |
| `TEAM_ALERTS_ATTACH_EXCEPTION_OVER` | Integer: send traceback as a **file** when longer than this many characters |
| `TEAM_ALERTS_ENV_METADATA` | Comma-separated env var **names** to copy into alert metadata when present |
| `TEAM_ALERTS_METADATA_URL_STYLE` | `markdown` (or `md` / `labeled`) for `[key](url)` metadata links; omit or any other value for `<url>` |
| `TEAM_ALERTS_ALERT_BANNER` | `0` / `false` / `off` disables the top separator; any other non-empty string is a **custom** banner line (omit for the built-in default) |
| `TEAM_ALERTS_USE_EMBEDS` | **Default: embeds on** when unset. Set to `0` / `false` / `no` / `off` / `plain` / `raw` for plain `content` only; `1` / `true` / `yes` / `on` / `embed` forces embeds |
| `TEAM_ALERTS_ALERT_FOOTER` | Plain-text footer appended to the **last** webhook when an alert is split across multiple posts |
| `TEAM_ALERTS_EMBED_FOOTER` | Optional short embed footer line (embed mode) |
| `TEAM_ALERTS_ALLOWED_ROLE_IDS` | Comma-separated role snowflakes for `allowed_mentions` |
| `TEAM_ALERTS_ALLOWED_USER_IDS` | Comma-separated user snowflakes for `allowed_mentions` |
| `TEAM_ALERTS_ALLOW_EVERYONE_MENTION` | Must be `1` / `true` to allow `@everyone` (off by default) |
| `TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS` | Max HTTP attempts per webhook POST (default `3`); `1` disables retries |

### `.env.local` for pytest

If you create a **`.env.local`** file at the project root (same directory as `pyproject.toml`), pytest loads it automatically before tests run. Use the usual `KEY=value` or `export KEY=value` lines; values can be single- or double-quoted.

Variables already set in your shell take precedence (`setdefault`), so you can override file values when needed.

`.env.local` is listed in `.gitignore` so it is not committed.

## Delivery semantics

- **Single POST**: Each `requests.post` to the webhook URL is **one delivery attempt** (or more if retries are enabled for that same payload; see `DiscordTransportOptions.webhook_max_attempts`). Success means Discord returned a **2xx** response for that POST.
- **Plain mode**: Long alerts are **not** split across multiple webhook posts. If the formatted body exceeds Discord’s ``2000``-character ``content`` limit, a **single** multipart post sends a short notice plus the full body as **`message.txt`**. When a traceback is sent as a file (``attach_exception_over_chars`` threshold), the traceback and full alert text are delivered in **one** multipart post as two attachments—no follow-up ``content`` chunks.
- **Embed mode (default)**: Short ``Alert.message`` text is **inlined in the embed description** (under the header block) and the request is a normal JSON webhook post when no file is needed. **Multipart** is used when the message is too long for a single embed description (4096 chars), when metadata + message exceed Discord’s **6000**-character total embed budget (the body then moves to **`message.txt`**), when the formatted traceback cannot fit in one ``Exception`` embed field (fenced code block under Discord’s per-field limit), when ``attach_exception_over_chars`` is set and the traceback is longer than that threshold, or when several of these apply. Discord’s clients often show **uploaded files above the embed card** on the same message; keeping the narrative in the embed when it fits avoids that layout for the main text.
- **Multipart + follow-ups** (long traceback as a file, then extra `content` posts): The same rule applies per HTTP call—the first multipart post and each JSON follow-up are independent.
- **Correlation fields**: Set `Alert.correlation_id`, `run_id`, and/or `dedupe_key` so every continuation chunk (and the embed description) carries the same identifiers, which makes partial deliveries easier to match to logs or tickets.

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

- **HTTP retries**: `DiscordTransportOptions.webhook_max_attempts` (default `3`), exponential backoff with jitter, and `Retry-After` on **429** are applied **per POST** inside `_post_payload` / `_post_multipart`, so a failed chunk of a split alert does not re-send chunks that already succeeded. Tune delays via `webhook_retry_base_delay_seconds`, `webhook_retry_max_delay_seconds`, and `webhook_retry_jitter_seconds`, or set `TEAM_ALERTS_WEBHOOK_MAX_ATTEMPTS=1` in the environment to disable retries.
- **Alert identity**: Optional `Alert.correlation_id`, `run_id`, and `dedupe_key` render in the plain-text header and embed description; continuation webhook payloads (plain split or embed overflow tails) repeat a compact marker so partial deliveries stay attributable.
- Formatting lives in `team_alerts.formatters`; transports stay focused on HTTP and optional enrichment.
- Metadata values that look like a single `http(s)` URL are sent as **clickable** links: default ``<url>`` (no preview), or ``[metadata_key](url)`` when ``DiscordTransportOptions.metadata_url_link_style="markdown"`` (closing ``)`` in URLs is percent-escaped for Discord markdown).
- Each Discord post from ``DiscordTransport`` starts with a **banner line** (see ``DEFAULT_ALERT_BANNER_LINE`` in ``constants``) so consecutive alerts are easier to scan; only the **first** chunk includes it when a message is split (one newline after the banner, no extra blank line). Disable with ``alert_banner=""``.
- **Embeds** (default ``use_embeds=True``): embed color follows severity; the description starts with the same **header** block (severity bar, service, env, ids, when) and then the **message body** when it fits. If the body is too long for one embed description or the whole embed would exceed the **6000**-character cap, the description switches to headers plus a pointer and the full body is **`message.txt`**. Metadata becomes titled fields; ``Alert.occurred_at`` sets embed ``timestamp`` and a **When:** line. The embed **title** is your ``Alert.title`` or ``Alert`` if unset. Tracebacks are an **Exception** embed field when the formatted text fits in one field (under Discord’s per-field limit with a fenced code block) and is not longer than ``attach_exception_over_chars`` when that option is set; otherwise they are **`traceback.txt`** on the same multipart post as the embed. Set ``Alert.discord_payload_style="plain"`` for one-off classic text, or ``use_embeds=False`` on the transport to default the whole client to plain posts.
- **Plain text** (``use_embeds=False`` or ``discord_payload_style="plain"``): same severity line + level bar and separate **Service** / **Environment** rows; optional top **banner**; a single ``content`` post when short enough, otherwise **one** multipart post with ``message.txt`` (no multi-chunk ``content`` sequence).
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
