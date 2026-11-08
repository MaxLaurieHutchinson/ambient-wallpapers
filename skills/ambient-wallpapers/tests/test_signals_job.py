import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class SignalJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile_path = self.root / "profile.json"
        self.profile = {
            "version": 1, "enabled": True, "allow_apply": True,
            "asset_root": ".", "signal_inbox": "signals.json",
            "context_sources": {"weather": ["daily-weather"], "agent": ["dot"]},
            "signals": {"allowed": ["weather"]},
            "weather": {"enabled": True, "city": "Exampleton", "country_code": "GB", "refresh_minutes": 60},
        }
        self.now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        self.applier = Mock(return_value={"status": "UNCHANGED"})
        self.fetcher = Mock(return_value={"city": "Exampleton", "tag": "rain", "weather_code": 61, "source": "open-meteo"})
        self.publisher = Mock(return_value={"tags": ["rain"]})

    def run_job(self, context=None):
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")
        import signals_job
        return signals_job.run_job(
            self.profile_path, now=self.now, fetcher=self.fetcher,
            applier=self.applier, publisher=self.publisher,
            context_reader=Mock(return_value=context or {}),
        )

    def test_paused_profile_does_not_fetch_or_apply(self):
        self.profile["enabled"] = False
        result = self.run_job()
        self.assertEqual(result["status"], "DISABLED")
        self.fetcher.assert_not_called()
        self.applier.assert_not_called()

    def test_no_network_without_weather_opt_in(self):
        self.profile["weather"]["enabled"] = False
        self.run_job()
        self.fetcher.assert_not_called()
        self.applier.assert_called_once()

    def test_weather_refresh_publishes_a_bounded_category(self):
        result = self.run_job()
        self.fetcher.assert_called_once_with("Exampleton", country_code="GB")
        self.publisher.assert_called_once()
        self.assertEqual(self.publisher.call_args.kwargs["tags"], ["rain"])
        self.assertEqual(self.publisher.call_args.kwargs["source"], "daily-weather")
        self.assertEqual(result["weather"]["status"], "UPDATED")

    def test_recent_weather_cache_avoids_another_request(self):
        result = self.run_job({"weather": {"observed_at": "2026-01-01T11:45:00+00:00", "tags": ["cloudy"]}})
        self.assertEqual(result["weather"]["status"], "CACHED")
        self.fetcher.assert_not_called()
        self.applier.assert_called_once()

    def test_weather_failure_keeps_wallpaper_selection_available(self):
        self.fetcher.side_effect = OSError("network unavailable")
        result = self.run_job()
        self.assertEqual(result["weather"]["status"], "UNAVAILABLE")
        self.publisher.assert_not_called()
        self.applier.assert_called_once()

    def test_job_receipt_reports_apply_failure(self):
        self.applier.return_value = {"status": "APPLY_FAILED", "detail": "not confirmed"}
        result = self.run_job()
        self.assertEqual(result["status"], "APPLY_FAILED")
        receipt = json.loads((self.root / "signals-job-latest.json").read_text())
        self.assertEqual(receipt["wallpaper"]["status"], "APPLY_FAILED")


if __name__ == "__main__":
    unittest.main()
