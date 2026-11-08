"""Offline tests for the opt-in Open-Meteo city weather signal."""

from __future__ import annotations

import json
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import weather_signal  # noqa: E402
except ModuleNotFoundError:
    weather_signal = None


class WeatherSignalAvailabilityTests(unittest.TestCase):
    def test_weather_signal_module_exists(self) -> None:
        self.assertIsNotNone(weather_signal, "weather_signal.py has not been implemented")


class WeatherSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        if weather_signal is None:
            self.skipTest("weather_signal.py has not been implemented")
        self.responses = [
            {"results": [{
                "name": "Exampleton",
                "country": "United Kingdom",
                "country_code": "GB",
                "admin1": "England",
                "latitude": 51.4543,
                "longitude": -0.9781,
            }]},
            {"current": {
                "time": "2026-11-08T08:00",
                "weather_code": 61,
            }},
        ]
        self.requests: list[tuple[str, float]] = []

    def opener(self, url: str, *, timeout: float) -> object:
        self.requests.append((url, timeout))
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        return _JsonResponse(self.responses.pop(0))

    def test_fetch_city_weather_geocodes_with_country_and_returns_inert_tag(self) -> None:
        result = weather_signal.fetch_city_weather("Exampleton", country_code="gb", opener=self.opener)

        self.assertEqual(result, {
            "city": "Exampleton, England, United Kingdom",
            "tag": "rain",
            "weather_code": 61,
            "observed_at": "2026-11-08T08:00:00+00:00",
            "source": "open-meteo",
        })
        self.assertEqual(len(self.requests), 2)
        geocode = urlsplit(self.requests[0][0])
        self.assertEqual(geocode.netloc, "geocoding-api.open-meteo.com")
        self.assertEqual(geocode.path, "/v1/search")
        query = parse_qs(geocode.query)
        self.assertEqual(query["name"], ["Exampleton"])
        self.assertEqual(query["countryCode"], ["GB"])
        self.assertEqual(query["count"], ["10"])
        weather = urlsplit(self.requests[1][0])
        self.assertEqual(weather.netloc, "api.open-meteo.com")
        self.assertEqual(weather.path, "/v1/forecast")
        weather_query = parse_qs(weather.query)
        self.assertEqual(weather_query["current"], ["weather_code"])
        self.assertEqual(weather_query["timezone"], ["UTC"])
        self.assertTrue(all(0 < timeout <= 8 for _, timeout in self.requests))

    def test_city_is_normalized_and_city_and_country_in_name_are_supported(self) -> None:
        result = weather_signal.fetch_city_weather(" Exampleton ", country_code="GB", opener=self.opener)
        self.assertEqual(result["city"], "Exampleton, England, United Kingdom")

        self.setUp()
        result = weather_signal.fetch_city_weather("Exampleton, GB", opener=self.opener)
        self.assertEqual(result["city"], "Exampleton, England, United Kingdom")
        self.assertEqual(parse_qs(urlsplit(self.requests[0][0]).query)["name"], ["Exampleton"])
        self.assertEqual(parse_qs(urlsplit(self.requests[0][0]).query)["countryCode"], ["GB"])

    def test_invalid_input_is_rejected_before_network_access(self) -> None:
        for city, country in (("", "GB"), ("R", "GB"), ("Exampleton", "GBR"), ("Exampleton", "1B")):
            with self.subTest(city=city, country=country):
                with self.assertRaises(ValueError):
                    weather_signal.fetch_city_weather(city, country_code=country, opener=self.opener)
        self.assertEqual(self.requests, [])

    def test_missing_and_ambiguous_city_fail_closed(self) -> None:
        self.responses[0] = {"results": []}
        with self.assertRaises(weather_signal.CityNotFoundError):
            weather_signal.fetch_city_weather("Exampleton", country_code="GB", opener=self.opener)

        self.responses = [{"results": [
            {"name": "Exampleton", "country": "United Kingdom", "country_code": "GB",
             "admin1": "England", "latitude": 51.45, "longitude": -0.97},
            {"name": "Exampleton", "country": "United States", "country_code": "US",
             "admin1": "Pennsylvania", "latitude": 40.34, "longitude": -75.93},
        ]}]
        with self.assertRaises(weather_signal.AmbiguousCityError):
            weather_signal.fetch_city_weather("Exampleton", opener=self.opener)

    def test_geocoder_fuzzy_results_do_not_make_exact_city_ambiguous(self) -> None:
        self.responses[0] = {"results": [
            {"name": "Exampleton", "country": "United Kingdom", "country_code": "GB",
             "admin1": "England", "latitude": 51.45, "longitude": -0.97},
            {"name": "Exampleton Street", "country": "United Kingdom", "country_code": "GB",
             "admin1": "Kent", "latitude": 51.04, "longitude": 0.2},
            {"name": "Exampleton", "country": "United States", "country_code": "US",
             "admin1": "Pennsylvania", "latitude": 40.34, "longitude": -75.93},
        ]}
        result = weather_signal.fetch_city_weather("Exampleton", country_code="GB", opener=self.opener)
        self.assertEqual(result["city"], "Exampleton, England, United Kingdom")

    def test_duplicate_exact_city_in_country_fails_with_region_hint(self) -> None:
        self.responses[0] = {"results": [
            {"name": "Exampleton", "country": "United Kingdom", "country_code": "GB",
             "admin1": "England", "latitude": 51.45, "longitude": -0.97},
            {"name": "Exampleton", "country": "United Kingdom", "country_code": "GB",
             "admin1": "Scotland", "latitude": 56.34, "longitude": -4.6},
            {"name": "Exampleton Street", "country": "United Kingdom", "country_code": "GB",
             "admin1": "Kent", "latitude": 51.04, "longitude": 0.2},
        ]}
        with self.assertRaisesRegex(weather_signal.AmbiguousCityError, "England.*Scotland"):
            weather_signal.fetch_city_weather("Exampleton", country_code="GB", opener=self.opener)

    def test_every_supported_weather_class_maps_to_a_safe_tag(self) -> None:
        cases = {
            0: "clear", 1: "cloudy", 3: "cloudy", 45: "fog", 48: "fog",
            51: "rain", 61: "rain", 82: "rain", 71: "snow", 86: "snow",
            95: "storm", 96: "storm", 99: "storm",
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.assertEqual(weather_signal.classify_weather_code(code), expected)

    def test_unknown_code_and_malformed_weather_fail_closed(self) -> None:
        with self.assertRaisesRegex(weather_signal.WeatherDataError, "Unsupported WMO"):
            weather_signal.classify_weather_code(999)
        for current in ({"time": "2026-11-08T08:00", "weather_code": 999},
                        {"time": "not-a-date", "weather_code": 61},
                        {"time": "2026-11-08T08:00"},
                        {"time": "2026-11-08T08:00", "weather_code": True}):
            with self.subTest(current=current):
                self.setUp()
                self.responses[1] = {"current": current}
                with self.assertRaises(weather_signal.WeatherDataError):
                    weather_signal.fetch_city_weather("Exampleton", country_code="GB", opener=self.opener)

    def test_invalid_geocoding_coordinates_fail_closed(self) -> None:
        self.responses[0]["results"][0]["latitude"] = 91
        with self.assertRaisesRegex(weather_signal.WeatherDataError, "coordinates"):
            weather_signal.fetch_city_weather("Exampleton", country_code="GB", opener=self.opener)

    def test_network_and_invalid_json_errors_are_safe_and_clear(self) -> None:
        def network_failure(url: str, *, timeout: float) -> object:
            raise URLError("offline")

        with self.assertRaisesRegex(weather_signal.WeatherSignalError, "Open-Meteo request failed"):
            weather_signal.fetch_city_weather("Exampleton", country_code="GB", opener=network_failure)

        with self.assertRaisesRegex(weather_signal.WeatherSignalError, "invalid JSON"):
            weather_signal.fetch_city_weather(
                "Exampleton", country_code="GB", opener=lambda *_args, **_kwargs: _RawResponse(b"{"))

    def test_cli_emits_json_and_supports_country_code_without_external_access(self) -> None:
        parsed = weather_signal._parser().parse_args(["--city", "Exampleton", "--country-code", "GB"])
        self.assertEqual((parsed.city, parsed.country_code), ("Exampleton", "GB"))
        expected = {"city": "Exampleton, England, United Kingdom", "tag": "rain", "weather_code": 61,
                    "observed_at": "2026-11-08T08:00:00+00:00", "source": "open-meteo"}
        with patch.object(weather_signal, "fetch_city_weather", return_value=expected) as fetch, \
                patch.object(weather_signal.sys, "stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(weather_signal.main(["--city", "Exampleton", "--country-code", "GB"]), 0)
        fetch.assert_called_once_with("Exampleton", country_code="GB")
        self.assertEqual(json.loads(stdout.getvalue()), expected)


class _JsonResponse:
    def __init__(self, value: dict[str, object]) -> None:
        self.body = json.dumps(value).encode("utf-8")

    def __enter__(self) -> "_JsonResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class _RawResponse(_JsonResponse):
    def __init__(self, body: bytes) -> None:
        self.body = body


if __name__ == "__main__":
    unittest.main()
