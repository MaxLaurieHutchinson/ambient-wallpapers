"""macOS adapter contract tests: no OS mutation or Swift runtime required."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ambient  # noqa: E402


class MacOSAdapterContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pictures = {}
        for name in ["laptop.png", "external.png"]:
            picture = self.root / name
            picture.write_bytes(b"synthetic image")
            self.pictures[name] = str(picture)
        self.assignments = {"laptop": self.pictures["laptop.png"],
                            "monitors": [self.pictures["external.png"]],
                            "display_roles": {}}
        self.expected = [
            {"DevicePath": "10", "WallpaperPath": self.pictures["laptop.png"]},
            {"DevicePath": "20", "WallpaperPath": self.pictures["external.png"]},
        ]

    def test_macos_apply_passes_plan_token_and_preserves_receipt(self):
        calls = []
        token = "a" * 64
        def fake_call(script, mode, **kwargs):
            calls.append((mode, kwargs))
            if mode == "Plan":
                return {"Result": "Planned", "PlanID": token, "Assignment": self.expected}
            return {"Result": "Applied", "StatePath": "/private/backup/state.json",
                    "Assignment": self.expected}
        with patch.object(ambient, "_call_macos", side_effect=fake_call):
            outcome = ambient.macos_apply(self.root / "macos_wallpaper.swift",
                                           self.assignments, self.root / "backup")
        self.assertTrue(outcome["verified"])
        self.assertEqual([c[0] for c in calls], ["Plan", "Apply"])
        self.assertEqual(calls[1][1]["plan_id"], token)
        self.assertEqual(calls[1][1]["assignment"], self.assignments)
        self.assertEqual(calls[1][1]["backup_root"], self.root / "backup")

    def test_macos_rejects_missing_or_mismatched_plan(self):
        def without_token(script, mode, **kwargs):
            return {"Result": "Planned", "Assignment": self.expected}
        with patch.object(ambient, "_call_macos", side_effect=without_token) as call:
            outcome = ambient.macos_apply(self.root / "adapter.swift", self.assignments, self.root)
        self.assertFalse(outcome["verified"])
        call.assert_called_once()
        mismatch = [
            {"DevicePath": "10", "WallpaperPath": self.pictures["external.png"]},
            {"DevicePath": "20", "WallpaperPath": self.pictures["laptop.png"]},
        ]
        with patch.object(ambient, "_call_macos", side_effect=[
            {"Result": "Planned", "PlanID": "b" * 64, "Assignment": self.expected},
            {"Result": "Applied", "Assignment": mismatch},
        ]):
            outcome = ambient.macos_apply(self.root / "adapter.swift", self.assignments, self.root)
        self.assertFalse(outcome["verified"])

    def test_mac_uses_connected_displays_and_saves_rollback_receipt(self):
        profile = {
            "version": 1, "enabled": True, "allow_apply": True,
            "asset_root": str(self.root), "fallback_pack": "set",
            "signals": {"allowed": []}, "display_roles": {},
            "catalog": [{"id": "set", "approved": True, "tags": ["day", "mobile", "docked"],
                         "laptop": "laptop.png", "monitors": ["external.png"]}]
        }
        state = self.root / "runtime-state.json"
        def invoke(script, mode, **kwargs):
            self.assertEqual(mode, "Inspect")
            return {"Result": "Inspected", "Monitors": [
                {"Connected": True, "DevicePath": "10"},
                {"Connected": True, "DevicePath": "20"},
            ]}
        def applied(script, assignment, backup_root):
            return {"verified": True, "result": "Applied",
                    "detail": {"apply": {"StatePath": "/private/backup/state.json"}}}
        with patch.object(ambient.sys, "platform", "darwin"), \
             patch.object(ambient, "_call_macos", side_effect=invoke), \
             patch.object(ambient, "macos_apply", side_effect=applied) as native:
            result = ambient.apply_profile(profile, state_path=state)
        self.assertEqual(result["status"], "APPLIED")
        self.assertTrue(native.called)
        saved = json.loads(state.read_text())
        self.assertEqual(saved["display_ids"], ["10", "20"])
        self.assertEqual(saved["restore_state_path"], "/private/backup/state.json")

    def test_non_mac_linux_apply_still_refused(self):
        profile = {
            "version": 1, "enabled": True, "allow_apply": True,
            "asset_root": str(self.root), "fallback_pack": "set",
            "signals": {"allowed": []},
            "catalog": [{"id": "set", "approved": True,
                         "laptop": "laptop.png", "monitors": ["external.png"]}]
        }
        with patch.object(ambient.sys, "platform", "linux"):
            with self.assertRaisesRegex(ambient.ProfileError, "Windows and macOS only"):
                ambient.apply_profile(profile, state_path=self.root / "state.json")

    def test_helper_invokes_swift_without_shell_and_handles_failures(self):
        adapter = self.root / "macos_wallpaper.swift"
        adapter.write_text("// synthetic", encoding="utf-8")
        completed = type("Completed", (), {"returncode": 0, "stdout": '{"Result":"Inspected","Monitors":[]}', "stderr": ""})()
        with patch.object(ambient.shutil, "which", return_value="/usr/bin/swift"), \
             patch.object(ambient.subprocess, "run", return_value=completed) as command:
            response = ambient._call_macos(adapter, "Inspect")
        self.assertEqual(response["Result"], "Inspected")
        self.assertFalse(command.call_args.kwargs["shell"])
        self.assertEqual(command.call_args.args[0][:4],
                         ["/usr/bin/swift", str(adapter), "--mode", "Inspect"])
        with patch.object(ambient.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ambient.ProfileError, "Swift toolchain"):
                ambient._call_macos(adapter, "Inspect")


if __name__ == "__main__":
    unittest.main()
