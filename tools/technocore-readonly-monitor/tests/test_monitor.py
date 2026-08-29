from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import technocore_monitor as monitor


class MonitorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_config(self, **updates: object) -> monitor.Config:
        payload: dict[str, object] = {
            "base_url": "https://technocore.chat",
            "rooms": ["technocore"],
            "state_file": ".state/state.json",
            "outbox_dir": "outbox",
            "bootstrap": "latest",
            "include_keywords": ["task", "help wanted"],
            "exclude_keywords": [],
            "mentions": ["bobbymarc00"],
            "sender_allowlist": [],
            "ignore_senders": [],
            "minimum_score": 1,
            "notify_stdout": False,
            "max_notifications_per_run": 10,
            "telegram": {"enabled": False},
        }
        payload.update(updates)
        path = self.root / "config.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return monitor.load_config(path)


class ConfigTests(MonitorTestCase):
    def test_load_config_resolves_paths_from_config_directory(self) -> None:
        config = self.make_config()
        self.assertEqual(config.state_file, self.root / ".state" / "state.json")
        self.assertEqual(config.outbox_dir, self.root / "outbox")
        self.assertEqual(config.rooms, ("technocore",))

    def test_rejects_invalid_room(self) -> None:
        with self.assertRaisesRegex(monitor.MonitorError, "invalid Technocore room"):
            self.make_config(rooms=["Bad Room"])

    def test_rejects_non_https_remote_origin(self) -> None:
        with self.assertRaisesRegex(monitor.MonitorError, "must use HTTPS"):
            self.make_config(base_url="http://example.com")

    def test_allows_loopback_http_for_tests(self) -> None:
        config = self.make_config(base_url="http://127.0.0.1:8080")
        self.assertEqual(config.base_url, "http://127.0.0.1:8080")

    def test_rejects_origin_with_credentials(self) -> None:
        with self.assertRaisesRegex(monitor.MonitorError, "must not contain credentials"):
            self.make_config(base_url="https://user:pass@example.com")

    def test_request_timeout_must_exceed_long_poll(self) -> None:
        with self.assertRaisesRegex(monitor.MonitorError, "must be greater"):
            self.make_config(long_poll_seconds=10, request_timeout_seconds=10)


class FilteringTests(MonitorTestCase):
    def test_keyword_match_scores_one(self) -> None:
        config = self.make_config()
        result = monitor.match_message(
            {"from": "did:key:z6Mkexample", "text": "There is a new task"}, config
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.score, 1)
        self.assertIn("keyword: task", result.reasons)

    def test_keyword_does_not_match_inside_longer_word(self) -> None:
        config = self.make_config(mentions=[])
        result = monitor.match_message(
            {"from": "agent", "text": "This is tasking, not a task request"},
            config,
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.reasons.count("keyword: task"), 1)

    def test_sender_name_does_not_trigger_keyword(self) -> None:
        config = self.make_config(mentions=[])
        result = monitor.match_message({"from": "taskbot", "text": "hello"}, config)
        self.assertFalse(result.matched)

    def test_mention_scores_three(self) -> None:
        config = self.make_config(minimum_score=3)
        result = monitor.match_message(
            {"from": "agent", "text": "Can bobbymarc00 review this?"}, config
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.score, 3)

    def test_exclusion_takes_precedence(self) -> None:
        config = self.make_config(exclude_keywords=["spam"])
        result = monitor.match_message(
            {"from": "agent", "text": "task spam"}, config
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.score, 0)

    def test_ignored_sender_is_skipped(self) -> None:
        config = self.make_config(ignore_senders=["did:key:z6MkMine"])
        result = monitor.match_message(
            {"from": "did:key:z6MkMine", "text": "task"}, config
        )
        self.assertFalse(result.matched)

    def test_no_positive_rules_matches_all(self) -> None:
        config = self.make_config(include_keywords=[], mentions=[], sender_allowlist=[])
        result = monitor.match_message({"from": "any", "text": "hello"}, config)
        self.assertTrue(result.matched)
        self.assertEqual(result.reasons, ("all messages enabled",))

    def test_display_sanitizer_removes_control_characters(self) -> None:
        cleaned = monitor.sanitize_display("hello\x1b[31m\nworld\u202e", 100)
        self.assertNotIn("\x1b", cleaned)
        self.assertNotIn("\n", cleaned)
        self.assertNotIn("\u202e", cleaned)
        self.assertIn("hello", cleaned)
        self.assertIn("world", cleaned)

    def test_formatted_alert_keeps_template_line_breaks(self) -> None:
        config = self.make_config()
        alert = monitor.message_alert(
            config,
            "technocore",
            1,
            {"seq": 7, "ts": "2026-08-29T00:00:00Z", "from": "agent", "text": "task"},
            monitor.MatchResult(True, 1, ("keyword: task",)),
        )
        rendered = monitor.format_alert(alert, 1200)
        self.assertIn("\nRoom: technocore\n", rendered)
        self.assertIn("\nNo reply was sent.", rendered)

    def test_formatted_alert_keeps_review_footer_for_long_message(self) -> None:
        config = self.make_config()
        alert = monitor.message_alert(
            config,
            "technocore",
            1,
            {
                "seq": 8,
                "ts": "2026-08-29T00:00:00Z",
                "from": "agent",
                "text": "x" * 4096,
            },
            monitor.MatchResult(True, 1, ("keyword: task",)),
        )
        rendered = monitor.format_alert(alert, 1200)
        self.assertLessEqual(len(rendered), 1200)
        self.assertIn("\nReview: https://technocore.chat/humans#r/technocore/8\n", rendered)
        self.assertTrue(rendered.endswith("No reply was sent."))


class ProtocolTests(MonitorTestCase):
    def valid_view(self) -> dict[str, object]:
        return {
            "room": "technocore",
            "count": 2,
            "first_seq": 10,
            "last_seq": 11,
            "generation": 3,
            "messages": [
                {"seq": 10, "ts": "2026-08-29T00:00:00Z", "from": "a", "text": "one"},
                {"seq": 11, "ts": "2026-08-29T00:00:01Z", "from": "b", "text": "two"},
            ],
        }

    def test_parses_official_room_view(self) -> None:
        parsed = monitor.parse_room_view(self.valid_view(), "technocore")
        self.assertEqual(parsed["last_seq"], 11)
        self.assertEqual(len(parsed["messages"]), 2)

    def test_rejects_wrong_room(self) -> None:
        payload = self.valid_view()
        payload["room"] = "lobby"
        with self.assertRaisesRegex(monitor.MonitorError, "does not match"):
            monitor.parse_room_view(payload, "technocore")

    def test_rejects_inconsistent_count(self) -> None:
        payload = self.valid_view()
        payload["count"] = 999
        with self.assertRaisesRegex(monitor.MonitorError, "count is inconsistent"):
            monitor.parse_room_view(payload, "technocore")

    def test_rejects_out_of_order_sequences(self) -> None:
        payload = self.valid_view()
        payload["messages"] = list(reversed(payload["messages"]))
        with self.assertRaisesRegex(monitor.MonitorError, "not strictly ordered"):
            monitor.parse_room_view(payload, "technocore")

    @mock.patch("technocore_monitor.request_json")
    @mock.patch("technocore_monitor.time.time", return_value=123.456)
    def test_fetch_uses_only_official_read_query(
        self, _mock_time: mock.Mock, mock_request: mock.Mock
    ) -> None:
        mock_request.return_value = self.valid_view()
        config = self.make_config(long_poll_seconds=5)
        monitor.fetch_room(config, "technocore", 9)
        url = mock_request.call_args.args[0]
        self.assertIn("/r/technocore?", url)
        self.assertIn("format=json", url)
        self.assertIn("since=9", url)
        self.assertIn("wait=5.0", url)
        self.assertNotIn("/say/", url)
        self.assertNotIn("say-signed", url)


class PersistenceTests(MonitorTestCase):
    def test_state_round_trip(self) -> None:
        path = self.root / ".state" / "state.json"
        state = monitor.empty_state()
        state["rooms"]["technocore"] = {"last_seq": 42, "generation": 1}
        monitor.save_state(path, state)
        loaded = monitor.load_state(path)
        self.assertEqual(loaded["rooms"]["technocore"]["last_seq"], 42)
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_corrupt_state_is_not_silently_reset(self) -> None:
        path = self.root / "state.json"
        path.write_text("not-json", encoding="utf-8")
        with self.assertRaisesRegex(monitor.MonitorError, "instead of silently resetting"):
            monitor.load_state(path)

    def test_outbox_does_not_overwrite_existing_alert(self) -> None:
        alert = {"id": "technocore:technocore:g1:s7", "status": "needs_human_review"}
        first_path, first_created = monitor.write_alert(self.root / "outbox", alert)
        first_path.write_text(
            '{"id":"technocore:technocore:g1:s7","status":"manually-reviewed"}\n',
            encoding="utf-8",
        )
        second_path, second_created = monitor.write_alert(self.root / "outbox", alert)
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first_path, second_path)
        self.assertIn("manually-reviewed", second_path.read_text(encoding="utf-8"))

    def test_corrupt_outbox_item_is_not_silently_overwritten(self) -> None:
        alert = {"id": "technocore:technocore:g1:s8", "status": "needs_human_review"}
        path, _created = monitor.write_alert(self.root / "outbox", alert)
        path.write_text("broken", encoding="utf-8")
        with self.assertRaisesRegex(monitor.MonitorError, "instead of overwriting"):
            monitor.write_alert(self.root / "outbox", alert)


class WorkflowTests(MonitorTestCase):
    def room_view(self, messages: list[dict[str, object]], since: int = 0) -> dict[str, object]:
        return {
            "room": "technocore",
            "count": len(messages),
            "first_seq": messages[0]["seq"] if messages else None,
            "last_seq": messages[-1]["seq"] if messages else since,
            "generation": 1,
            "messages": messages,
        }

    @mock.patch("technocore_monitor.fetch_room")
    def test_latest_bootstrap_sets_cursor_without_alerting(self, mock_fetch: mock.Mock) -> None:
        config = self.make_config(bootstrap="latest")
        mock_fetch.return_value = self.room_view(
            [{"seq": 50, "ts": "2026-08-29T00:00:00Z", "from": "a", "text": "task"}]
        )
        state = monitor.empty_state()
        alerts, scanned, errors = monitor.process_room(config, state, "technocore")
        self.assertEqual((alerts, scanned, errors), (0, 1, []))
        self.assertEqual(state["rooms"]["technocore"]["last_seq"], 50)
        self.assertFalse(config.outbox_dir.exists())

    @mock.patch("technocore_monitor.fetch_room")
    def test_idle_run_is_silent_on_stdout(self, mock_fetch: mock.Mock) -> None:
        config = self.make_config()
        mock_fetch.return_value = self.room_view([], since=0)

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = monitor.run_once(config)

        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "")

    @mock.patch("technocore_monitor.notify")
    @mock.patch("technocore_monitor.fetch_room")
    def test_notification_budget_caps_delivery(
        self, mock_fetch: mock.Mock, mock_notify: mock.Mock
    ) -> None:
        config = self.make_config(
            max_notifications_per_run=1,
            notify_stdout=True,
        )
        state = monitor.empty_state()
        state["rooms"]["technocore"] = {"last_seq": 0, "generation": 1}
        mock_fetch.return_value = self.room_view(
            [
                {"seq": 1, "ts": "2026-08-29T00:00:00Z", "from": "a", "text": "new task"},
                {"seq": 2, "ts": "2026-08-29T00:00:01Z", "from": "b", "text": "another task"},
            ],
            since=0,
        )

        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            alerts, scanned, errors = monitor.process_room(config, state, "technocore")

        self.assertEqual((alerts, scanned, errors), (2, 2, []))
        self.assertEqual(mock_notify.call_count, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(len(list(config.outbox_dir.glob("*.json"))), 2)

    @mock.patch("technocore_monitor.fetch_room")
    def test_new_matching_message_creates_review_item(self, mock_fetch: mock.Mock) -> None:
        config = self.make_config()
        state = monitor.empty_state()
        state["rooms"]["technocore"] = {"last_seq": 50, "generation": 1}
        mock_fetch.return_value = self.room_view(
            [{"seq": 51, "ts": "2026-08-29T00:00:00Z", "from": "agent", "text": "new task"}],
            since=50,
        )
        alerts, scanned, errors = monitor.process_room(config, state, "technocore")
        self.assertEqual((alerts, scanned, errors), (1, 1, []))
        files = list(config.outbox_dir.glob("*.json"))
        self.assertEqual(len(files), 1)
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "needs_human_review")
        self.assertFalse(payload["safety"]["reply_sent"])
        self.assertFalse(payload["safety"]["signing_key_accessed"])

    @mock.patch("technocore_monitor.fetch_room")
    def test_sequence_gap_creates_warning(self, mock_fetch: mock.Mock) -> None:
        config = self.make_config(include_keywords=["not-present"], mentions=[])
        state = monitor.empty_state()
        state["rooms"]["technocore"] = {"last_seq": 10, "generation": 1}
        mock_fetch.return_value = self.room_view(
            [{"seq": 15, "ts": "2026-08-29T00:00:00Z", "from": "agent", "text": "hello"}],
            since=10,
        )
        alerts, _scanned, errors = monitor.process_room(config, state, "technocore")
        self.assertEqual(errors, [])
        self.assertEqual(alerts, 1)
        payload = json.loads(next(config.outbox_dir.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(payload["system_event"]["title"], "Sequence gap detected")


if __name__ == "__main__":
    unittest.main()
