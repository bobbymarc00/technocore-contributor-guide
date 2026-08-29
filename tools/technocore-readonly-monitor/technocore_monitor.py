#!/usr/bin/env python3
"""Read-only Technocore room monitor with a human-review outbox.

This program only reads Technocore room endpoints. It contains no signing code,
does not load an identity, and never posts a message back to Technocore.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import json
import os
import random
import re
import socket
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


VERSION = "0.1.0"
ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TELEGRAM_RESPONSE_BYTES = 64 * 1024
STATE_SCHEMA_VERSION = 1
ALERT_SCHEMA_VERSION = 1


class MonitorError(RuntimeError):
    """A safe, user-facing monitor error."""


class RetryableError(MonitorError):
    """A transient error that a watch loop may retry."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class NotificationError(MonitorError):
    """A notification could not be delivered."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Refuse redirects so a configured origin cannot silently change."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


HTTP_OPENER = build_opener(NoRedirectHandler())


@dataclasses.dataclass(frozen=True)
class TelegramConfig:
    enabled: bool
    bot_token_env: str
    chat_id_env: str


@dataclasses.dataclass(frozen=True)
class Config:
    config_path: Path
    base_url: str
    rooms: tuple[str, ...]
    state_file: Path
    outbox_dir: Path
    poll_seconds: float
    long_poll_seconds: float
    request_timeout_seconds: float
    limit: int
    bootstrap: str
    include_keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...]
    mentions: tuple[str, ...]
    sender_allowlist: tuple[str, ...]
    ignore_senders: tuple[str, ...]
    minimum_score: int
    notify_stdout: bool
    max_alert_chars: int
    max_notifications_per_run: int
    telegram: TelegramConfig


@dataclasses.dataclass(frozen=True)
class MatchResult:
    matched: bool
    score: int
    reasons: tuple[str, ...]


@dataclasses.dataclass
class NotificationBudget:
    remaining: int

    def take(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


def utc_now() -> str:
    """Return a compact UTC timestamp."""

    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise MonitorError(f"{name} must be true or false")
    return value


def _require_number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MonitorError(f"{name} must be a number")
    result = float(value)
    if not minimum <= result <= maximum:
        raise MonitorError(f"{name} must be between {minimum:g} and {maximum:g}")
    return result


def _require_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MonitorError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise MonitorError(f"{name} must be between {minimum} and {maximum}")
    return value


def _string_list(value: Any, name: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise MonitorError(f"{name} must be an array of strings")
    cleaned = tuple(item.strip() for item in value if item.strip())
    if not allow_empty and not cleaned:
        raise MonitorError(f"{name} must contain at least one value")
    return cleaned


def validate_base_url(value: Any) -> str:
    """Require HTTPS, except explicit loopback HTTP used for local tests."""

    if not isinstance(value, str) or not value.strip():
        raise MonitorError("base_url must be a non-empty string")
    raw = value.strip().rstrip("/")
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    loopback = host in {"localhost", "127.0.0.1", "::1"}
    if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
        raise MonitorError("base_url must use HTTPS (loopback HTTP is allowed for testing)")
    if not host or parts.username is not None or parts.password is not None:
        raise MonitorError("base_url must contain a host and must not contain credentials")
    if parts.query or parts.fragment:
        raise MonitorError("base_url must not contain a query string or fragment")
    if parts.path not in {"", "/"}:
        raise MonitorError("base_url must be an origin without an extra path")
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _resolve_path(config_path: Path, value: Any, name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise MonitorError(f"{name} must be a non-empty path string")
    path = Path(value).expanduser()
    return path if path.is_absolute() else (config_path.parent / path).resolve()


def load_config(path: Path) -> Config:
    """Load and strictly validate a JSON configuration file."""

    config_path = path.expanduser().resolve()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise MonitorError(f"configuration file not found: {config_path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise MonitorError(f"cannot read configuration file: {error}") from error
    if not isinstance(raw, dict):
        raise MonitorError("configuration root must be a JSON object")

    rooms = _string_list(raw.get("rooms"), "rooms", allow_empty=False)
    invalid_rooms = [room for room in rooms if not ROOM_RE.fullmatch(room)]
    if invalid_rooms:
        raise MonitorError(f"invalid Technocore room name: {invalid_rooms[0]!r}")
    if len(set(rooms)) != len(rooms):
        raise MonitorError("rooms must not contain duplicates")

    bootstrap = raw.get("bootstrap", "latest")
    if bootstrap not in {"latest", "backfill"}:
        raise MonitorError("bootstrap must be either 'latest' or 'backfill'")

    telegram_raw = raw.get("telegram", {})
    if not isinstance(telegram_raw, dict):
        raise MonitorError("telegram must be a JSON object")
    token_env = telegram_raw.get("bot_token_env", "TELEGRAM_BOT_TOKEN")
    chat_env = telegram_raw.get("chat_id_env", "TELEGRAM_CHAT_ID")
    env_name_re = re.compile(r"^[A-Z_][A-Z0-9_]*$")
    if not isinstance(token_env, str) or not env_name_re.fullmatch(token_env):
        raise MonitorError("telegram.bot_token_env must be an uppercase environment name")
    if not isinstance(chat_env, str) or not env_name_re.fullmatch(chat_env):
        raise MonitorError("telegram.chat_id_env must be an uppercase environment name")

    long_poll_seconds = _require_number(
        raw.get("long_poll_seconds", 0), "long_poll_seconds", 0, 10
    )
    request_timeout_seconds = _require_number(
        raw.get("request_timeout_seconds", 20), "request_timeout_seconds", 1, 120
    )
    if request_timeout_seconds <= long_poll_seconds:
        raise MonitorError("request_timeout_seconds must be greater than long_poll_seconds")

    return Config(
        config_path=config_path,
        base_url=validate_base_url(raw.get("base_url")),
        rooms=rooms,
        state_file=_resolve_path(config_path, raw.get("state_file", ".state/state.json"), "state_file"),
        outbox_dir=_resolve_path(config_path, raw.get("outbox_dir", "outbox"), "outbox_dir"),
        poll_seconds=_require_number(raw.get("poll_seconds", 30), "poll_seconds", 1, 86400),
        long_poll_seconds=long_poll_seconds,
        request_timeout_seconds=request_timeout_seconds,
        limit=_require_int(raw.get("limit", 200), "limit", 1, 200),
        bootstrap=bootstrap,
        include_keywords=_string_list(raw.get("include_keywords", []), "include_keywords"),
        exclude_keywords=_string_list(raw.get("exclude_keywords", []), "exclude_keywords"),
        mentions=_string_list(raw.get("mentions", []), "mentions"),
        sender_allowlist=_string_list(raw.get("sender_allowlist", []), "sender_allowlist"),
        ignore_senders=_string_list(raw.get("ignore_senders", []), "ignore_senders"),
        minimum_score=_require_int(raw.get("minimum_score", 1), "minimum_score", 1, 100),
        notify_stdout=_require_bool(raw.get("notify_stdout", True), "notify_stdout"),
        max_alert_chars=_require_int(
            raw.get("max_alert_chars", 1200), "max_alert_chars", 600, 3500
        ),
        max_notifications_per_run=_require_int(
            raw.get("max_notifications_per_run", 10),
            "max_notifications_per_run",
            1,
            100,
        ),
        telegram=TelegramConfig(
            enabled=_require_bool(telegram_raw.get("enabled", False), "telegram.enabled"),
            bot_token_env=token_env,
            chat_id_env=chat_env,
        ),
    )


def sanitize_display(value: Any, max_chars: int = 4096) -> str:
    """Make untrusted public text safe for terminals and plain-text notifiers."""

    text = value if isinstance(value, str) else str(value)
    swept = "".join(
        " "
        if unicodedata.category(character) in {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}
        else character
        for character in text
    )
    compact = " ".join(swept.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max(0, max_chars - 1)].rstrip() + "…"


def _contains_term(text: str, term: str) -> bool:
    parts = term.casefold().split()
    if not parts:
        return False
    pattern = r"\s+".join(re.escape(part) for part in parts)
    return re.search(rf"(?<!\w){pattern}(?!\w)", text.casefold()) is not None


def match_message(message: dict[str, Any], config: Config) -> MatchResult:
    """Score a message with deterministic rules; no message becomes an instruction."""

    sender = str(message.get("from", ""))
    text = str(message.get("text", ""))

    ignored = {item.casefold() for item in config.ignore_senders}
    if sender.casefold() in ignored:
        return MatchResult(False, 0, ("ignored sender",))

    excluded = [term for term in config.exclude_keywords if _contains_term(text, term)]
    if excluded:
        return MatchResult(False, 0, (f"excluded keyword: {excluded[0]}",))

    score = 0
    reasons: list[str] = []
    for mention in config.mentions:
        if _contains_term(text, mention):
            score += 3
            reasons.append(f"mention: {mention}")
    for keyword in config.include_keywords:
        if _contains_term(text, keyword):
            score += 1
            reasons.append(f"keyword: {keyword}")
    if sender.casefold() in {item.casefold() for item in config.sender_allowlist}:
        score += 2
        reasons.append("allowlisted sender")

    no_positive_rules = not (
        config.mentions or config.include_keywords or config.sender_allowlist
    )
    if no_positive_rules:
        score = 1
        reasons.append("all messages enabled")
    return MatchResult(score >= config.minimum_score, score, tuple(reasons))


def parse_room_view(payload: Any, expected_room: str) -> dict[str, Any]:
    """Validate the subset of the official JSON response the monitor consumes."""

    if not isinstance(payload, dict):
        raise MonitorError("Technocore returned a non-object JSON response")
    if payload.get("room") != expected_room:
        raise MonitorError("Technocore response room does not match the requested room")
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise MonitorError("Technocore response is missing a messages array")
    parsed: list[dict[str, Any]] = []
    previous_seq = 0
    for item in messages:
        if not isinstance(item, dict):
            raise MonitorError("Technocore returned a malformed message")
        seq = item.get("seq")
        sender = item.get("from")
        text = item.get("text")
        timestamp = item.get("ts")
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
            raise MonitorError("Technocore returned a message with an invalid seq")
        if seq <= previous_seq:
            raise MonitorError("Technocore messages are not strictly ordered by seq")
        if (
            not isinstance(sender, str)
            or not isinstance(text, str)
            or not isinstance(timestamp, str)
        ):
            raise MonitorError("Technocore returned a message with invalid fields")
        parsed.append({**item, "seq": seq, "from": sender, "text": text, "ts": timestamp})
        previous_seq = seq

    last_seq = payload.get("last_seq")
    first_seq = payload.get("first_seq")
    generation = payload.get("generation", 0)
    if isinstance(last_seq, bool) or not isinstance(last_seq, int) or last_seq < 0:
        raise MonitorError("Technocore response has an invalid last_seq")
    if first_seq is not None and (
        isinstance(first_seq, bool) or not isinstance(first_seq, int) or first_seq < 1
    ):
        raise MonitorError("Technocore response has an invalid first_seq")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise MonitorError("Technocore response has an invalid generation")
    if parsed and (first_seq != parsed[0]["seq"] or last_seq != parsed[-1]["seq"]):
        raise MonitorError("Technocore response sequence metadata is inconsistent")
    if not parsed and first_seq is not None:
        raise MonitorError("Technocore response sequence metadata is inconsistent")
    count = payload.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(parsed):
        raise MonitorError("Technocore response count is inconsistent")
    return {
        "room": expected_room,
        "count": len(parsed),
        "first_seq": first_seq,
        "last_seq": last_seq,
        "generation": generation,
        "messages": parsed,
    }


def _retry_after(error: HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    if value is None:
        return None
    try:
        return max(0.0, min(float(value), 300.0))
    except ValueError:
        return None


def request_json(url: str, timeout: float, max_bytes: int = MAX_RESPONSE_BYTES) -> Any:
    """Fetch bounded JSON without following redirects."""

    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": f"technocore-readonly-monitor/{VERSION}"},
        method="GET",
    )
    try:
        with HTTP_OPENER.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
    except HTTPError as error:
        if error.code == 429:
            raise RetryableError("Technocore read rate limit reached", _retry_after(error)) from error
        if 500 <= error.code <= 599:
            raise RetryableError(f"Technocore temporarily returned HTTP {error.code}") from error
        if 300 <= error.code <= 399:
            raise MonitorError(f"Technocore redirect refused (HTTP {error.code})") from error
        raise MonitorError(f"Technocore returned HTTP {error.code}") from error
    except (URLError, TimeoutError, socket.timeout) as error:
        raise RetryableError("Technocore request failed or timed out") from error
    if len(body) > max_bytes:
        raise MonitorError("Technocore response exceeded the safe size limit")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MonitorError("Technocore returned invalid JSON") from error


def fetch_room(config: Config, room: str, since: int | None) -> dict[str, Any]:
    query: dict[str, str | int | float] = {
        "format": "json",
        "limit": config.limit,
        "n": int(time.time() * 1000),
    }
    if since is not None:
        query["since"] = since
        if config.long_poll_seconds:
            query["wait"] = config.long_poll_seconds
    url = f"{config.base_url}/r/{room}?{urlencode(query)}"
    payload = request_json(url, config.request_timeout_seconds)
    view = parse_room_view(payload, room)
    if since is not None:
        if view["last_seq"] < since or any(
            message["seq"] <= since for message in view["messages"]
        ):
            raise MonitorError("Technocore response did not honor the requested sequence cursor")
    return view


def empty_state() -> dict[str, Any]:
    return {"schema_version": STATE_SCHEMA_VERSION, "rooms": {}}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MonitorError(
            f"state file is unreadable; repair or move it instead of silently resetting: {path}"
        ) from error
    if not isinstance(raw, dict) or raw.get("schema_version") != STATE_SCHEMA_VERSION:
        raise MonitorError("state file has an unsupported schema version")
    rooms = raw.get("rooms")
    if not isinstance(rooms, dict):
        raise MonitorError("state file has an invalid rooms object")
    for room, entry in rooms.items():
        if not isinstance(room, str) or not isinstance(entry, dict):
            raise MonitorError("state file contains a malformed room entry")
        last_seq = entry.get("last_seq")
        generation = entry.get("generation", 0)
        if (
            isinstance(last_seq, bool)
            or not isinstance(last_seq, int)
            or last_seq < 0
            or isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 0
        ):
            raise MonitorError("state file contains invalid sequence metadata")
    return raw


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON with restrictive permissions and atomic replacement."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), 0o600)
            else:
                os.chmod(temporary_path, 0o600)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except Exception:
        with contextlib.suppress(OSError):
            temporary_path.unlink()
        raise


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    atomic_write_json(path, state)


@contextlib.contextmanager
def monitor_lock(state_file: Path) -> Iterator[None]:
    """Prevent overlapping Linux cron/systemd runs from racing the cursor."""

    lock_path = state_file.with_suffix(state_file.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            pass
        except BlockingIOError as error:
            raise MonitorError("another monitor process already holds the state lock") from error
        yield
    finally:
        handle.close()


def message_alert(
    config: Config,
    room: str,
    generation: int,
    message: dict[str, Any],
    match: MatchResult,
) -> dict[str, Any]:
    seq = message["seq"]
    return {
        "schema_version": ALERT_SCHEMA_VERSION,
        "id": f"technocore:{room}:g{generation}:s{seq}",
        "status": "needs_human_review",
        "created_at": utc_now(),
        "source": {
            "service": "technocore",
            "base_url": config.base_url,
            "room": room,
            "seq": seq,
            "generation": generation,
            "permalink": f"{config.base_url}/humans#r/{room}/{seq}",
        },
        "message": {
            "from": message["from"],
            "timestamp": message["ts"],
            "text": sanitize_display(message["text"], 4096),
        },
        "match": {"score": match.score, "reasons": list(match.reasons)},
        "safety": {
            "content_is_untrusted": True,
            "reply_sent": False,
            "signing_key_accessed": False,
        },
    }


def system_alert(
    config: Config,
    room: str,
    generation: int,
    event_id: str,
    title: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "schema_version": ALERT_SCHEMA_VERSION,
        "id": f"technocore:{room}:g{generation}:{event_id}",
        "status": "needs_human_review",
        "created_at": utc_now(),
        "source": {
            "service": "technocore",
            "base_url": config.base_url,
            "room": room,
            "generation": generation,
            "permalink": f"{config.base_url}/humans#r/{room}",
        },
        "system_event": {"title": title, "detail": detail},
        "safety": {
            "content_is_untrusted": False,
            "reply_sent": False,
            "signing_key_accessed": False,
        },
    }


def _safe_alert_filename(alert_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", alert_id).strip("-") + ".json"


def write_alert(outbox_dir: Path, alert: dict[str, Any]) -> tuple[Path, bool]:
    """Create one immutable review item; return false when it already exists."""

    outbox_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = outbox_dir / _safe_alert_filename(str(alert["id"]))
    if destination.exists():
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MonitorError(
                f"existing outbox item is unreadable; repair it instead of overwriting: {destination}"
            ) from error
        if not isinstance(existing, dict) or existing.get("id") != alert["id"]:
            raise MonitorError(f"existing outbox item has an unexpected identity: {destination}")
        return destination, False
    fd: int | None = None
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            json.dump(alert, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(outbox_dir)
    except FileExistsError:
        if fd is not None:
            os.close(fd)
        return write_alert(outbox_dir, alert)
    except Exception:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(OSError):
            destination.unlink()
        raise
    return destination, True


def _short_sender(sender: str) -> str:
    if sender.startswith("did:key:") and len(sender) > 24:
        return f"{sender[:18]}…{sender[-6:]}"
    return sanitize_display(sender, 80)


def format_alert(alert: dict[str, Any], max_chars: int) -> str:
    source = alert["source"]
    if "message" in alert:
        message = alert["message"]
        reasons = ", ".join(alert.get("match", {}).get("reasons", [])) or "configured rule"
        message_budget = max(100, max_chars - 500)
        body = (
            "Technocore alert — human review required\n"
            f"Room: {source['room']}\n"
            f"Sequence: {source['seq']}\n"
            f"From: {_short_sender(message['from'])}\n"
            f"Matched: {sanitize_display(reasons, 240)}\n"
            f"Message: {sanitize_display(message['text'], message_budget)}\n"
            f"Review: {source['permalink']}\n"
            "No reply was sent."
        )
    else:
        event = alert["system_event"]
        detail_budget = max(100, max_chars - 350)
        body = (
            "Technocore monitor warning\n"
            f"Room: {source['room']}\n"
            f"Event: {sanitize_display(event['title'], 120)}\n"
            f"Detail: {sanitize_display(event['detail'], detail_budget)}\n"
            f"Review: {source['permalink']}\n"
            "No reply was sent."
        )
    if len(body) <= max_chars:
        return body
    return body[: max_chars - 1].rstrip() + "…"


def send_telegram(config: Config, text: str) -> None:
    token = os.environ.get(config.telegram.bot_token_env)
    chat_id = os.environ.get(config.telegram.chat_id_env)
    if not token or not chat_id:
        raise NotificationError(
            "Telegram is enabled but its token or chat ID environment variable is missing"
        )
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": f"technocore-readonly-monitor/{VERSION}",
        },
        method="POST",
    )
    try:
        with HTTP_OPENER.open(request, timeout=config.request_timeout_seconds) as response:
            response_body = response.read(MAX_TELEGRAM_RESPONSE_BYTES + 1)
        if len(response_body) > MAX_TELEGRAM_RESPONSE_BYTES:
            raise NotificationError("Telegram returned an oversized response")
        result = json.loads(response_body.decode("utf-8"))
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise NotificationError("Telegram rejected the notification")
    except HTTPError as error:
        raise NotificationError(f"Telegram notification failed with HTTP {error.code}") from error
    except (URLError, TimeoutError, socket.timeout, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NotificationError("Telegram notification failed or returned invalid data") from error


def notify(config: Config, alert: dict[str, Any]) -> list[str]:
    text = format_alert(alert, config.max_alert_chars)
    errors: list[str] = []
    if config.notify_stdout:
        print(text, flush=True)
    if config.telegram.enabled:
        try:
            send_telegram(config, text)
        except NotificationError as error:
            errors.append(str(error))
    return errors


def _emit_alert(
    config: Config, alert: dict[str, Any], budget: NotificationBudget
) -> tuple[bool, list[str]]:
    path, created = write_alert(config.outbox_dir, alert)
    if not created:
        return False, []
    if not config.notify_stdout and not config.telegram.enabled:
        return True, []
    if not budget.take():
        return True, []
    errors = notify(config, alert)
    return True, errors


def process_room(
    config: Config,
    state: dict[str, Any],
    room: str,
    budget: NotificationBudget | None = None,
) -> tuple[int, int, list[str]]:
    """Process one room and return (new alerts, scanned messages, errors)."""

    room_state = state["rooms"].get(room)
    first_run = room_state is None
    since = (
        None
        if first_run and config.bootstrap == "latest"
        else int((room_state or {}).get("last_seq", 0))
    )
    view = fetch_room(config, room, since)
    generation = view["generation"]
    budget = budget or NotificationBudget(config.max_notifications_per_run)
    errors: list[str] = []
    alerts_created = 0

    if first_run and config.bootstrap == "latest":
        state["rooms"][room] = {
            "last_seq": view["last_seq"],
            "generation": generation,
            "updated_at": utc_now(),
        }
        save_state(config.state_file, state)
        print(
            f"Initialized {room} at sequence {view['last_seq']} (historical messages skipped)",
            file=sys.stderr,
            flush=True,
        )
        return 0, len(view["messages"]), []

    previous_seq = int((room_state or {}).get("last_seq", 0))
    previous_generation = int((room_state or {}).get("generation", generation))
    if room_state is not None and generation != previous_generation:
        alert = system_alert(
            config,
            room,
            generation,
            f"generation-change-{previous_generation}-to-{generation}",
            "Room generation changed",
            f"Stored generation {previous_generation}; current generation {generation}. Review room context before acting.",
        )
        created, notify_errors = _emit_alert(config, alert, budget)
        alerts_created += int(created)
        errors.extend(notify_errors)

    first_seq = view["first_seq"]
    if first_seq is not None and first_seq > previous_seq + 1:
        missed = first_seq - previous_seq - 1
        alert = system_alert(
            config,
            room,
            generation,
            f"sequence-gap-{previous_seq + 1}-to-{first_seq - 1}",
            "Sequence gap detected",
            f"At least {missed} message(s) were not returned between sequences {previous_seq} and {first_seq}. The room may have advanced beyond the 200-message read window.",
        )
        created, notify_errors = _emit_alert(config, alert, budget)
        alerts_created += int(created)
        errors.extend(notify_errors)

    for message in view["messages"]:
        match = match_message(message, config)
        if not match.matched:
            continue
        alert = message_alert(config, room, generation, message, match)
        created, notify_errors = _emit_alert(config, alert, budget)
        alerts_created += int(created)
        errors.extend(notify_errors)

    state["rooms"][room] = {
        "last_seq": max(previous_seq, view["last_seq"]),
        "generation": generation,
        "updated_at": utc_now(),
    }
    save_state(config.state_file, state)
    return alerts_created, len(view["messages"]), errors


def run_once(config: Config) -> int:
    """Poll all configured rooms once."""

    with monitor_lock(config.state_file):
        state = load_state(config.state_file)
        failed_rooms = 0
        delivery_errors: list[str] = []
        total_alerts = 0
        total_scanned = 0
        budget = NotificationBudget(config.max_notifications_per_run)
        for room in config.rooms:
            try:
                alerts, scanned, errors = process_room(
                    config, state, room, budget
                )
                total_alerts += alerts
                total_scanned += scanned
                delivery_errors.extend(errors)
            except RetryableError as error:
                failed_rooms += 1
                suffix = (
                    f"; retry after about {error.retry_after:g}s"
                    if error.retry_after
                    else ""
                )
                print(f"{room}: {error}{suffix}", file=sys.stderr, flush=True)
            except (MonitorError, OSError) as error:
                failed_rooms += 1
                print(f"{room}: {error}", file=sys.stderr, flush=True)
        if total_alerts or failed_rooms or delivery_errors:
            print(
                f"Run complete: {total_scanned} message(s) scanned, {total_alerts} review item(s) created",
                file=sys.stderr,
                flush=True,
            )
        for error in delivery_errors:
            print(f"notification warning: {error}", file=sys.stderr, flush=True)
        return 1 if failed_rooms or delivery_errors else 0


def run_watch(config: Config) -> int:
    """Run forever with bounded exponential backoff after errors."""

    failures = 0
    while True:
        code = run_once(config)
        failures = failures + 1 if code else 0
        base_delay = config.poll_seconds if not failures else min(
            config.poll_seconds * (2 ** min(failures, 5)), 300
        )
        delay = base_delay + random.uniform(0, min(base_delay * 0.1, 5))
        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            print("Monitor stopped", flush=True)
            return 0


def print_check(config: Config) -> None:
    """Print a secret-free configuration summary."""

    summary = {
        "version": VERSION,
        "base_url": config.base_url,
        "rooms": list(config.rooms),
        "state_file": str(config.state_file),
        "outbox_dir": str(config.outbox_dir),
        "bootstrap": config.bootstrap,
        "max_notifications_per_run": config.max_notifications_per_run,
        "telegram_enabled": config.telegram.enabled,
        "technocore_write_capability": False,
        "identity_or_signing_key_required": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read Technocore rooms and create human-review alerts without signing or posting."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument(
        "--config", type=Path, default=Path("config.json"), help="JSON configuration path"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="poll each room once (default)")
    mode.add_argument("--watch", action="store_true", help="poll continuously")
    mode.add_argument(
        "--check", action="store_true", help="validate configuration without network access"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.check:
            print_check(config)
            return 0
        if args.watch:
            return run_watch(config)
        return run_once(config)
    except KeyboardInterrupt:
        print("Monitor stopped", file=sys.stderr)
        return 130
    except (MonitorError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
