"""Refresh an opted-in city weather cache, then select approved local wallpapers."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import ambient


def _receipt(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_job(profile_path: Path, *, now=None, fetcher=None, applier=None,
            publisher=None, context_reader=None) -> dict:
    profile, profile_path = ambient.load_profile(profile_path)
    if not profile.get("enabled") or not profile.get("allow_apply"):
        return {"status": "DISABLED", "reason": "Automatic selection/application is paused."}
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        raise ValueError("Job time must include a timezone.")
    current = current.astimezone(timezone.utc)
    if context_reader is None or publisher is None:
        from context_signals import publish_signal, read_signals
        context_reader = context_reader or read_signals
        publisher = publisher or publish_signal
    applier = applier or ambient.apply_profile
    inbox = Path(profile.get("signal_inbox", profile_path.with_name("signals.json")))
    if not inbox.is_absolute():
        inbox = profile_path.parent / inbox
    allowed_sources = profile.get("context_sources", {})
    weather = profile.get("weather", {})
    weather_result = {"status": "DISABLED"}
    opted_in = (weather.get("enabled") is True and
                "weather" in profile.get("signals", {}).get("allowed", []) and
                "daily-weather" in allowed_sources.get("weather", []))
    if opted_in:
        city = weather.get("city")
        if not isinstance(city, str) or not city.strip():
            raise ValueError("Weather requires a user-selected city.")
        interval = weather.get("refresh_minutes", 60)
        if type(interval) is not int or not 15 <= interval <= 1440:
            raise ValueError("weather.refresh_minutes must be 15 to 1440.")
        cached = context_reader(inbox, now=current, allowed_sources=allowed_sources).get("weather")
        observed = None
        if cached:
            observed = datetime.fromisoformat(cached["observed_at"].replace("Z", "+00:00"))
        if observed and (current - observed.astimezone(timezone.utc)).total_seconds() < interval * 60:
            weather_result = {"status": "CACHED", "tags": cached.get("tags", [])}
        else:
            try:
                if fetcher is None:
                    from weather_signal import fetch_city_weather
                    fetcher = fetch_city_weather
                value = fetcher(city.strip(), country_code=weather.get("country_code"))
                publisher(inbox, kind="weather", source="daily-weather", ttl_minutes=180,
                          tags=[value["tag"]], now=current)
                weather_result = {"status": "UPDATED", "city": value.get("city", city),
                                  "tag": value["tag"], "provider": value.get("source", "open-meteo")}
            except (OSError, ValueError, TimeoutError) as exc:
                weather_result = {"status": "UNAVAILABLE", "detail": str(exc)}
    outcome = applier(profile, state_path=profile_path.with_name(profile_path.stem + ".state.json"), now=current)
    result = {"status": outcome.get("status", "APPLY_FAILED"), "ran_at": current.isoformat(),
              "weather": weather_result, "wallpaper": outcome}
    _receipt(profile_path.with_name("signals-job-latest.json"), result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_job(args.profile)
        print(json.dumps(result, indent=2))
        return 1 if result.get("status") == "APPLY_FAILED" else 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "detail": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
