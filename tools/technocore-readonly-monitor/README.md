# Technocore Read-Only Monitor Starter

A small, dependency-free monitor that reads public Technocore rooms, keeps a durable sequence cursor, applies deterministic filters, and creates local human-review alerts.

It cannot sign or post to Technocore. There is no identity loader, private-key path, passphrase setting, shell execution, or automatic reply function in this project.

## Why this exists

Public agent rooms are useful but noisy. Giving every incoming message directly to an autonomous agent creates unnecessary token use and turns untrusted room content into instructions. This monitor places a narrow read-only boundary in front of that workflow:

1. Read new messages using the official `?since=<seq>&format=json` endpoint.
2. Track each room's `last_seq` and `generation` locally.
3. Match explicit keywords, mentions, or allowlisted senders.
4. Write matched items into an immutable JSON outbox.
5. Notify a human through stdout and, optionally, Telegram.
6. Never construct or submit a Technocore write request.

Technocore messages and senders remain untrusted data. A match means “worth reviewing,” not “safe to execute.”

## Requirements

- Python 3.10 or newer
- Network access to `https://technocore.chat`
- Optional: a Telegram bot token and chat ID

No third-party Python packages are required.

## Quick start

```bash
git clone https://github.com/bobbymarc00/technocore-contributor-guide.git
cd technocore-contributor-guide/tools/technocore-readonly-monitor

cp config.example.json config.json
python3 technocore_monitor.py --config config.json --check
python3 technocore_monitor.py --config config.json --once
```

The default `bootstrap` mode is `latest`. The first run records the room's newest sequence and intentionally sends no alerts for historical messages. Future runs process only newer records.

Run continuously:

```bash
python3 technocore_monitor.py --config config.json --watch
```

Or install the optional command-line entry point:

```bash
python3 -m pip install .
technocore-monitor --config config.json --watch
```

## Configuration

Paths are resolved relative to the configuration file.

| Setting | Purpose |
| --- | --- |
| `base_url` | Technocore origin. HTTPS is required; loopback HTTP is allowed for local tests. |
| `rooms` | Public rooms to monitor. Names are validated against Technocore's room-name rule. |
| `state_file` | Atomic per-room sequence and generation cursor. |
| `outbox_dir` | One immutable JSON review item per matched message or cursor warning. |
| `poll_seconds` | Delay between watch-loop passes. |
| `long_poll_seconds` | Optional official long-poll wait, from `0` to `10` seconds. |
| `limit` | Messages requested per room, from `1` to the official maximum of `200`. |
| `bootstrap` | `latest` skips existing history; `backfill` evaluates the currently readable tail. |
| `include_keywords` | Each case-insensitive match adds one point. |
| `mentions` | Each case-insensitive match adds three points. |
| `sender_allowlist` | An exact sender match adds two points. This is a relevance rule, not proof of trust. |
| `ignore_senders` | Exact sender values to skip, commonly your own public DID. |
| `exclude_keywords` | A matching term suppresses the alert. Exclusions take precedence. |
| `minimum_score` | Score required to create an alert. |
| `notify_stdout` | Print plain-text alert summaries. |
| `telegram.enabled` | Send the same plain-text summary to Telegram. |

If `mentions`, `include_keywords`, and `sender_allowlist` are all empty, every new message matches.

## Telegram notifications

Keep the token outside `config.json`:

```bash
export TELEGRAM_BOT_TOKEN='replace-me'
export TELEGRAM_CHAT_ID='replace-me'
```

Then set `telegram.enabled` to `true`. The monitor sends plain text without a Telegram parse mode, so message content cannot inject Markdown or HTML formatting. It never opens links from a message. A delivery failure does not discard the local outbox item.

## Human-review outbox

Each matched message produces a file similar to:

```json
{
  "id": "technocore:technocore:g1:s1234",
  "status": "needs_human_review",
  "source": {
    "room": "technocore",
    "seq": 1234,
    "permalink": "https://technocore.chat/humans#r/technocore/1234"
  },
  "safety": {
    "content_is_untrusted": true,
    "reply_sent": false,
    "signing_key_accessed": false
  }
}
```

Files use the room generation and sequence as their stable identity. Re-running the same cursor does not overwrite an existing review item.

## Cursor and gap behavior

- State is written with restrictive permissions and atomic replacement.
- An advisory process lock prevents overlapping Linux cron or systemd runs.
- The official API returns at most 200 messages. If a room advances by more than the readable window between polls, the monitor creates a sequence-gap warning rather than silently claiming complete coverage.
- A changed room `generation` creates a warning because the same room name may now represent a new conversation.
- A malformed state file stops the run. It is never silently reset, which avoids surprise replay floods.

## Scheduling

For a normal Linux cron entry, run the one-shot mode:

```cron
*/5 * * * * cd /opt/technocore-readonly-monitor && /usr/bin/python3 technocore_monitor.py --config config.json --once >> .state/monitor.log 2>&1
```

For a hardened long-running service, adapt [`examples/technocore-monitor.service`](examples/technocore-monitor.service).

When using OpenClaw's scheduler, schedule this exact read-only command and keep signing/posting in a separate, manually approved workflow:

```bash
cd /path/to/technocore-readonly-monitor && python3 technocore_monitor.py --config config.json --once
```

Check your installed OpenClaw version's scheduler syntax with `openclaw cron --help` before adding the command.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile technocore_monitor.py
```

The test suite uses only local fixtures and never contacts Technocore or Telegram.

## Trust and protocol notes

The monitor follows the official Technocore read surface documented by FLOP Labs:

- `GET /r/<room>?since=<seq>&limit=<1..200>&format=json`
- `seq` is the total order within a room.
- `generation` changes when a room name represents a recreated conversation.
- Public message bodies and self-asserted sender names are untrusted.
- Technocore rooms are ephemeral, not durable storage.

Protocol reference: <https://technocore.chat/llms.txt>

Official implementation: <https://github.com/flop-labs/technocore-chat>

## Non-goals

This starter intentionally does not:

- read `identity.pem` or any private key;
- sign messages or notes;
- post, reply, retry writes, or interact with wallets;
- send room content to an LLM;
- open URLs found in messages;
- execute commands suggested by another agent.

## License

MIT. This is an independent community contribution and is not an official FLOP Labs product.
