import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from accounts.store import org_status
from assistant.query_engine import QueryFilters, _filters_to_dict, _filter_jsonl_events
from config.plans import PLANS, plan_allows, within_limit
from dashboard.app import (
    CameraManager,
    LoginThrottle,
    aggregate_vehicle_events,
    event_in_org,
    validate_public_stream_url,
)


class _FakeService:
    def __init__(self, org_id):
        self.org_id = org_id
        self.closed = False


class PlansTests(unittest.TestCase):
    def test_within_limit(self):
        self.assertTrue(within_limit(None, 10**6))
        self.assertTrue(within_limit(3, 2))
        self.assertFalse(within_limit(3, 3))

    def test_features_by_plan(self):
        self.assertTrue(plan_allows("intelligence", "assistant"))
        self.assertFalse(plan_allows("report", "assistant"))
        self.assertTrue(plan_allows("report", "pdf"))
        self.assertFalse(plan_allows("insight", "assistant"))

    def test_every_plan_defines_all_limits(self):
        for key, plan in PLANS.items():
            for field in ("label", "max_users", "max_cameras", "pdf_per_month", "chat_per_month", "features"):
                self.assertIn(field, plan, f"{key} sem {field}")


class OrgStatusTests(unittest.TestCase):
    def test_status(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(org_status({"active": True, "plan_expires_at": None}), "active")
        self.assertEqual(org_status({"active": False, "plan_expires_at": None}), "inactive")
        self.assertEqual(org_status({"active": True, "plan_expires_at": (now - timedelta(days=1)).isoformat()}), "expired")
        self.assertEqual(org_status({"active": True, "plan_expires_at": (now + timedelta(days=1)).isoformat()}), "active")


class TenantIsolationTests(unittest.TestCase):
    def test_event_in_org(self):
        self.assertTrue(event_in_org({"org_id": 2}, None))
        self.assertTrue(event_in_org({"org_id": 2}, 2))
        self.assertFalse(event_in_org({"org_id": 2}, 3))
        # evento antigo (sem org_id) pertence à organização interna
        self.assertTrue(event_in_org({}, 1, legacy_org_id=1))
        self.assertFalse(event_in_org({}, 2, legacy_org_id=1))

    def test_camera_manager_hides_other_orgs(self):
        manager = CameraManager("modelo.pt")
        manager.services = {"cam_1": _FakeService(1), "cam_2": _FakeService(2)}
        self.assertIsNotNone(manager.get("cam_1", 1))
        self.assertIsNone(manager.get("cam_1", 2))
        self.assertEqual([cid for cid, _ in manager.items(2)], ["cam_2"])
        self.assertEqual(len(manager.items()), 2)

    def test_jsonl_aggregation_is_scoped(self):
        now = datetime.now(timezone.utc).isoformat()
        lines = [
            {"timestamp": now, "type": "VEHICLE_DETECTED", "camera_id": "a", "class_name": "carro", "org_id": 1},
            {"timestamp": now, "type": "VEHICLE_DETECTED", "camera_id": "b", "class_name": "carro", "org_id": 2},
            {"timestamp": now, "type": "VEHICLE_DETECTED", "camera_id": "c", "class_name": "moto"},
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
            since = datetime.now(timezone.utc) - timedelta(hours=1)

            def total(**kwargs):
                return sum(bucket["total"] for bucket in aggregate_vehicle_events(path, since, **kwargs))

            self.assertEqual(total(), 3)
            self.assertEqual(total(org_id=2), 1)
            self.assertEqual(total(org_id=1, legacy_org_id=1), 2)  # inclui o evento sem org_id
            self.assertEqual(total(org_id=3), 0)

            events = _filter_jsonl_events(path, ("VEHICLE_DETECTED",), since, org_id=2)
            self.assertEqual([event["camera_id"] for event in events], ["b"])

    def test_filters_dict_does_not_expose_org(self):
        from datetime import date

        payload = _filters_to_dict(QueryFilters(date(2026, 1, 1), date(2026, 1, 2), org_id=7))
        self.assertNotIn("org_id", payload)


class RollingWindowTests(unittest.TestCase):
    def test_since_until_override_calendar_dates(self):
        from datetime import date

        from assistant.query_engine import _date_range

        since = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        until = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
        filters = QueryFilters(date(2026, 1, 1), date(2026, 1, 2), since=since, until=until)
        self.assertEqual(_date_range(filters), (since, until))
        self.assertNotIn("since", _filters_to_dict(filters))

    def test_window_summary_counts_only_inside_window(self):
        import os
        from unittest import mock

        from assistant.query_engine import window_summary

        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=10)).isoformat()
        recent = (now - timedelta(hours=2)).isoformat()
        lines = [
            {"timestamp": old, "type": "VEHICLE_DETECTED", "class_name": "carro", "camera_id": "a"},
            {"timestamp": recent, "type": "VEHICLE_DETECTED", "class_name": "moto", "camera_id": "a"},
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
            with mock.patch.dict(os.environ, {"DATABASE_BACKEND": ""}), mock.patch(
                "assistant.query_engine._events_path", return_value=path
            ):
                self.assertEqual(window_summary(now - timedelta(hours=24))["total_vehicles"], 1)
                self.assertEqual(window_summary(now - timedelta(days=30))["total_vehicles"], 2)
                self.assertEqual(window_summary(now - timedelta(days=30))["by_class"], {"carro": 1, "moto": 1})


class PasswordPolicyTests(unittest.TestCase):
    def test_policy(self):
        from accounts.store import validate_new_password

        validate_new_password("senha-boa-123", "a@b.com")
        for bad in ("curta", "a@b.com", "aaaaaaaaaaaa", "x" * 200):
            with self.assertRaises(ValueError, msg=bad):
                validate_new_password(bad, "a@b.com")


class StreamUrlTests(unittest.TestCase):
    def test_rejects_non_network_sources(self):
        for raw in ("0", "C:\\videos\\a.mp4", "/etc/passwd", "file:///etc/passwd", "ftp://example.com/a"):
            with self.assertRaises(ValueError, msg=raw):
                validate_public_stream_url(raw)

    def test_rejects_internal_addresses(self):
        for raw in (
            "rtsp://127.0.0.1/stream",
            "http://localhost:8080/video",
            "http://192.168.0.10/cam",
            "http://10.0.0.5/cam",
            "http://169.254.169.254/latest/meta-data",
            "rtsp://[::1]/stream",
        ):
            with self.assertRaises(ValueError, msg=raw):
                validate_public_stream_url(raw)

    def test_accepts_public_ip(self):
        self.assertEqual(validate_public_stream_url("rtsp://8.8.8.8:554/live"), "rtsp://8.8.8.8:554/live")


class LoginThrottleTests(unittest.TestCase):
    def test_blocks_after_max_failures_and_resets(self):
        throttle = LoginThrottle(max_attempts=3, window_seconds=60)
        key = ("1.2.3.4", "a@b.com")
        for _ in range(3):
            self.assertFalse(throttle.blocked(key))
            throttle.fail(key)
        self.assertTrue(throttle.blocked(key))
        throttle.reset(key)
        self.assertFalse(throttle.blocked(key))


if __name__ == "__main__":
    unittest.main()
