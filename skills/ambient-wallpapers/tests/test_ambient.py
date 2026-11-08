"""Behavior tests for cached wallpaper selection and safe apply state."""

from __future__ import annotations

import json
import contextlib
import io
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import ambient  # noqa: E402
except ModuleNotFoundError:
    ambient = None


class RuntimeAvailabilityTests(unittest.TestCase):
    def test_runtime_entrypoint_exists(self) -> None:
        self.assertIsNotNone(ambient, "ambient.py has not been implemented")


class AmbientPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        if ambient is None:
            self.skipTest("runtime entrypoint has not been implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.images = {}
        for name in ("day.png", "night.png", "rainy.png", "external-a.png", "external-b.png"):
            path = self.root / name
            path.write_bytes(b"image")
            self.images[name] = str(path)
        self.profile = {
            "version": 1,
            "enabled": True,
            "allow_apply": True,
            "asset_root": str(self.root),
            "fallback_pack": "day",
            "signals": {
                "allowed": ["time_of_day", "display_count", "weather", "agent"],
                "day_start": 7,
                "night_start": 19,
                "min_interval_minutes": 30,
            },
            "catalog": [
                {"id": "day", "approved": True, "tags": ["day", "mobile"],
                 "laptop": "day.png", "monitors": ["external-a.png", "external-b.png"]},
                {"id": "night", "approved": True, "tags": ["night", "mobile"],
                 "laptop": "night.png", "monitors": ["external-b.png", "external-a.png"]},
                {"id": "night-docked", "approved": True, "tags": ["night", "docked"],
                 "laptop": "night.png", "monitors": ["external-b.png", "external-a.png"]},
                {"id": "rainy", "approved": True, "tags": ["day", "mobile", "rain"],
                 "laptop": "rainy.png", "monitors": ["external-a.png"]},
                {"id": "draft", "approved": False, "tags": ["day", "mobile"],
                 "laptop": "night.png", "monitors": ["external-a.png"]},
            ],
        }
        self.now = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_selects_approved_pack_for_time_and_monitor_count(self) -> None:
        result = ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now)
        self.assertEqual(result["pack_id"], "day")
        self.assertEqual(result["assignments"], {
            "laptop": self.images["day.png"],
            "monitors": [self.images["external-a.png"], self.images["external-b.png"]],
            "display_roles": {},
        })
        self.assertEqual(result["status"], "READY")

        result = ambient.build_plan(self.profile, hour=21, display_count=3, now=self.now)
        self.assertEqual(result["pack_id"], "night-docked")
        self.assertEqual(result["assignments"]["monitors"], [
            self.images["external-b.png"], self.images["external-a.png"]
        ])

    def test_never_selects_unapproved_pack_and_uses_fallback_if_no_match(self) -> None:
        result = ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now,
                                    state={"pack_id": "draft"})
        self.assertEqual(result["pack_id"], "day")

    def test_no_enabled_signals_use_fallback(self) -> None:
        self.profile["signals"]["allowed"] = []
        result = ambient.build_plan(self.profile, hour=21, display_count=1, now=self.now)
        self.assertEqual(result["pack_id"], "day")

    def test_docked_plan_requires_monitor_wallpapers(self) -> None:
        self.profile["catalog"][0]["monitors"] = []
        with self.assertRaises(ambient.ProfileError):
            ambient.build_plan(self.profile, hour=8, display_count=2, now=self.now,
                               state={"pack_id": "day", "display_count": 2,
                                      "applied_at": "2026-01-05T07:55:00+00:00"})

    def test_manual_override_wins_until_expiry(self) -> None:
        self.profile["manual_override"] = {
            "pack_id": "night", "until": "2026-01-05T09:00:00+00:00"
        }
        self.assertEqual(ambient.build_plan(self.profile, hour=8, display_count=1,
                                            now=self.now)["pack_id"], "night")
        self.profile["manual_override"]["until"] = "2026-01-05T07:59:00+00:00"
        self.assertEqual(ambient.build_plan(self.profile, hour=8, display_count=1,
                                            now=self.now)["pack_id"], "day")

    def test_active_manual_override_bypasses_cooldown(self) -> None:
        self.profile["manual_override"] = {
            "pack_id": "night", "until": "2026-01-05T09:00:00+00:00"
        }
        result = ambient.build_plan(
            self.profile, hour=8, display_count=1, now=self.now,
            state={"pack_id": "day", "display_count": 1,
                   "applied_at": "2026-01-05T07:59:00+00:00"},
        )
        self.assertEqual(result["pack_id"], "night")
        self.assertEqual(result["status"], "READY")

    def test_weather_context_adds_only_known_weather_tag(self) -> None:
        result = ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now,
                                    context={"weather": {"tags": ["rain"]}})
        self.assertEqual(result["pack_id"], "rainy")
        self.assertIn("rain", result["signals"])
        invalid = ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now,
                                     context={"weather": {"tags": ["hurricane"]}})
        self.assertEqual(invalid["pack_id"], "day")

    def test_agent_preferred_pack_uses_approved_pack_and_ignores_unknown_hint(self) -> None:
        selected = ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now,
                                      context={"agent": {"preferred_pack": "night"}})
        self.assertEqual(selected["pack_id"], "night")
        unknown = ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now,
                                     context={"agent": {"preferred_pack": "draft"}})
        self.assertEqual(unknown["pack_id"], "day")
        self.assertIn("ignored", unknown["reason"].lower())
        self.profile["signals"]["allowed"].remove("agent")
        ignored_disabled = ambient.build_plan(
            self.profile, hour=8, display_count=1, now=self.now,
            context={"agent": {"preferred_pack": "night"}},
        )
        self.assertEqual(ignored_disabled["pack_id"], "day")

    def test_disabled_profile_returns_a_skip_plan(self) -> None:
        self.profile["enabled"] = False
        self.assertEqual(ambient.build_plan(self.profile, hour=8, display_count=1,
                                            now=self.now)["status"], "DISABLED")

    def test_asset_path_may_not_escape_asset_root(self) -> None:
        (self.root.parent / "outside.png").write_bytes(b"outside")
        self.profile["catalog"][0]["laptop"] = "../outside.png"
        with self.assertRaises(ambient.ProfileError):
            ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now)

    def test_missing_or_non_image_asset_is_rejected(self) -> None:
        self.profile["catalog"][0]["laptop"] = "missing.png"
        with self.assertRaises(ambient.ProfileError):
            ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now)

    def test_repeat_selection_is_idempotent_and_cooldown_holds_switch(self) -> None:
        recent = {"pack_id": "day", "display_count": 1,
                  "applied_at": "2026-01-05T07:59:00+00:00"}
        same = ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now, state=recent)
        self.assertEqual(same["status"], "UNCHANGED")

        change = ambient.build_plan(self.profile, hour=21, display_count=1, now=self.now, state=recent)
        self.assertEqual(change["status"], "COOLDOWN")

    def test_same_count_but_different_display_ids_is_not_unchanged(self) -> None:
        recent = {"pack_id": "day", "display_count": 2,
                  "display_ids": ["LAPTOP", "OLD-MONITOR"],
                  "applied_at": "2026-01-05T07:00:00+00:00"}
        changed = ambient.build_plan(self.profile, hour=8, display_count=2,
                                     display_ids=["LAPTOP", "NEW-MONITOR"],
                                     now=self.now, state=recent)
        self.assertEqual(changed["status"], "READY")

    def test_external_only_topology_keeps_full_monitor_image_catalog(self) -> None:
        result = ambient.build_plan(self.profile, hour=8, display_count=2, now=self.now)
        self.assertEqual(result["assignments"]["laptop"], self.images["day.png"])
        self.assertEqual(result["assignments"]["monitors"], [
            self.images["external-a.png"], self.images["external-b.png"]
        ])

    def test_explicit_display_roles_are_validated_and_passed_to_adapter(self) -> None:
        self.profile["display_roles"] = {"\\\\?\\DISPLAY#LAPTOP": "laptop"}
        result = ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now)
        self.assertEqual(result["assignments"]["display_roles"], self.profile["display_roles"])
        self.profile["display_roles"] = {"": "laptop"}
        with self.assertRaises(ambient.ProfileError):
            ambient.build_plan(self.profile, hour=8, display_count=1, now=self.now)


class ApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        AmbientPlanTests.setUp(self)

    def tearDown(self) -> None:
        AmbientPlanTests.tearDown(self)

    def test_apply_requires_both_explicit_enable_and_permission(self) -> None:
        self.profile["enabled"] = False
        calls = []
        with self.assertRaises(ambient.ProfileError):
            ambient.apply_profile(self.profile, state_path=self.root / "state.json",
                                  adapter=lambda assignment: calls.append(assignment))
        self.profile["enabled"] = True
        self.profile["allow_apply"] = False
        with self.assertRaises(ambient.ProfileError):
            ambient.apply_profile(self.profile, state_path=self.root / "state.json",
                                  adapter=lambda assignment: calls.append(assignment))
        self.assertEqual(calls, [])

    def test_writes_atomic_state_only_after_verified_apply(self) -> None:
        state_path = self.root / "state.json"
        failed = ambient.apply_profile(self.profile, state_path=state_path,
                                       adapter=lambda assignment: {"result": "Applied", "verified": False},
                                       hour=8, display_count=1, now=self.now)
        self.assertEqual(failed["status"], "APPLY_FAILED")
        self.assertFalse(state_path.exists())
        result = ambient.apply_profile(self.profile, state_path=state_path,
                                       adapter=lambda assignment: {
                                           "result": "Applied", "verified": True,
                                           "detail": {"plan": {"Assignment": []},
                                                      "apply": {"StatePath": str(self.root / "restore.json")}},
                                       },
                                       hour=8, display_count=1, now=self.now)
        self.assertEqual(result["status"], "APPLIED")
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["pack_id"], "day")
        self.assertEqual(saved["restore_state_path"], str(self.root / "restore.json"))
        self.assertIn("apply", saved["adapter_receipt"])
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_windows_apply_verifies_only_the_actual_plan_assignments(self) -> None:
        script = self.root / "adapter.ps1"
        expected_external_only = [{"DevicePath": "DISPLAY-A", "WallpaperPath": self.images["external-a.png"]}]
        expected_laptop_only = [{"DevicePath": "DISPLAY-LAPTOP", "WallpaperPath": self.images["day.png"]}]

        for expected in (expected_external_only, expected_laptop_only):
            with self.subTest(expected=expected):
                calls = []

                def adapter_call(_script, mode, **kwargs):
                    calls.append((mode, kwargs))
                    if mode == "Plan":
                        return {"Result": "Planned", "Assignment": expected}
                    return {"Result": "Applied", "Assignment": expected}

                with patch.object(ambient, "_call_windows", side_effect=adapter_call):
                    result = ambient.windows_apply(script, {
                        "laptop": self.images["day.png"],
                        "monitors": [self.images["external-a.png"], self.images["external-b.png"]],
                    }, self.root / "backup")

                self.assertTrue(result["verified"])
                self.assertEqual([call[0] for call in calls], ["Plan", "Apply"])

    def test_windows_apply_rejects_assignment_that_differs_from_read_only_plan(self) -> None:
        planned = [{"DevicePath": "DISPLAY-LAPTOP", "WallpaperPath": self.images["day.png"]}]
        applied = [{"DevicePath": "DISPLAY-EXTERNAL", "WallpaperPath": self.images["external-a.png"]}]

        def adapter_call(_script, mode, **kwargs):
            return {"Result": "Planned" if mode == "Plan" else "Applied",
                    "Assignment": planned if mode == "Plan" else applied}

        with patch.object(ambient, "_call_windows", side_effect=adapter_call):
            result = ambient.windows_apply(self.root / "adapter.ps1", {
                "laptop": self.images["day.png"], "monitors": [self.images["external-a.png"]],
            }, self.root / "backup")
        self.assertFalse(result["verified"])

    def test_cli_returns_nonzero_when_apply_reports_failure(self) -> None:
        profile_path = self.root / "profile.json"
        profile_path.write_text(json.dumps(self.profile), encoding="utf-8")
        output = io.StringIO()
        with patch.object(ambient.os, "name", "nt"), \
                patch.object(ambient, "apply_profile", return_value={"status": "APPLY_FAILED"}), \
                contextlib.redirect_stdout(output):
            exit_code = ambient.main(["apply", "--profile", str(profile_path)])
        self.assertNotEqual(exit_code, 0)

    def test_cli_reads_configured_cached_context_and_missing_inbox_is_graceful(self) -> None:
        profile_path = self.root / "profile.json"
        self.profile["signal_inbox"] = "signals/current.json"
        self.profile["context_sources"] = {
            "weather": ["daily-weather"], "agent": ["dot", "codex"]
        }
        profile_path.write_text(json.dumps(self.profile), encoding="utf-8")
        output = io.StringIO()
        with patch.object(ambient, "_read_signal_context", return_value={}) as read_context, \
                contextlib.redirect_stdout(output):
            exit_code = ambient.main(["plan", "--profile", str(profile_path), "--hour", "8"])
        self.assertEqual(exit_code, 0)
        read_context.assert_called_once()
        resolved_profile, _ = ambient.load_profile(profile_path)
        self.assertEqual(resolved_profile["signal_inbox"], str(self.root / "signals/current.json"))

    def test_context_reader_receives_allowlists_and_missing_inbox_returns_empty(self) -> None:
        inbox = self.root / "context.json"
        inbox.write_text("{}", encoding="utf-8")
        profile = {"signal_inbox": str(inbox), "context_sources": {
            "weather": ["daily-weather"], "agent": ["dot", "codex"]
        }}
        module = ModuleType("context_signals")
        captured = {}
        def read_signals(path, *, now, allowed_sources):
            captured.update(path=path, now=now, allowed_sources=allowed_sources)
            return {"weather": {"tags": ["rain"]}}
        module.read_signals = read_signals
        with patch.dict(sys.modules, {"context_signals": module}):
            result = ambient._read_signal_context(profile, now=self.now)
        self.assertEqual(result, {"weather": {"tags": ["rain"]}})
        self.assertEqual(captured["allowed_sources"], profile["context_sources"])
        self.assertEqual(captured["now"], self.now)
        self.assertEqual(ambient._read_signal_context({"signal_inbox": str(self.root / "missing.json")}), {})

    def test_context_signals_library_filters_sources_and_expired_events(self) -> None:
        inbox = self.root / "signals.json"
        inbox.write_text(json.dumps({"version": 1, "signals": [
            {"kind": "weather", "source": "daily-weather", "observed_at": "2026-01-05T07:00:00+00:00",
             "expires_at": "2026-01-05T09:00:00+00:00", "tags": ["rain"]},
            {"kind": "agent", "source": "unlisted", "observed_at": "2026-01-05T07:00:00+00:00",
             "expires_at": "2026-01-05T09:00:00+00:00", "tags": [], "preferred_pack": "night"},
            {"kind": "agent", "source": "dot", "observed_at": "2026-01-05T06:00:00+00:00",
             "expires_at": "2026-01-05T07:00:00+00:00", "tags": [], "preferred_pack": "night"},
        ]}), encoding="utf-8")
        result = ambient._read_signal_context({
            "signal_inbox": str(inbox),
            "context_sources": {"weather": ["daily-weather"], "agent": ["dot", "codex"]},
        }, now=self.now)
        self.assertEqual(result, {"weather": {
            "kind": "weather", "source": "daily-weather",
            "observed_at": "2026-01-05T07:00:00+00:00",
            "expires_at": "2026-01-05T09:00:00+00:00", "tags": ["rain"],
        }})


if __name__ == "__main__":
    unittest.main()
