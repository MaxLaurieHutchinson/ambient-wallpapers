"""Fetch a coarse, city-level weather tag from Open-Meteo.

This module deliberately has no location-service integration and does not write
wallpaper or signal files. Callers decide whether and how to use the returned
tag. Network access is limited to the two fixed Open-Meteo HTTPS endpoints.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen


TIMEOUT_SECONDS = 8
_GEOCODING_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_OPENER = Callable[..., Any]


class WeatherSignalError(ValueError):
    """Base error for an unavailable or invalid city weather signal."""


class CityNotFoundError(WeatherSignalError):
    """The geocoder returned no matching city."""


class AmbiguousCityError(WeatherSignalError):
    """The city name has multiple matches and needs a country code."""


class WeatherDataError(WeatherSignalError):
    """The geocoding or forecast response was malformed or unsupported."""


def _city_and_country(city: str, country_code: str | None) -> tuple[str, str | None]:
    if not isinstance(city, str):
        raise ValueError("city must be a string")
    city = city.strip()
    if "," in city:
        parts = [part.strip() for part in city.split(",")]
        if len(parts) != 2 or not parts[0] or not _COUNTRY_CODE.fullmatch(parts[1].upper()):
            raise ValueError("use a city name, optionally followed by a two-letter country code")
        if country_code is not None and country_code.upper() != parts[1].upper():
            raise ValueError("country code in city conflicts with country_code")
        country_code = parts[1]
        city = parts[0]
    if len(city) < 2:
        raise ValueError("city must contain at least two characters")
    if country_code is not None:
        if not isinstance(country_code, str) or not _COUNTRY_CODE.fullmatch(country_code.strip().upper()):
            raise ValueError("country_code must be a two-letter ISO country code")
        country_code = country_code.strip().upper()
    return city, country_code


def _read_json(url: str, opener: _OPENER) -> dict[str, Any]:
    try:
        with opener(url, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
    except (URLError, TimeoutError, OSError) as exc:
        raise WeatherSignalError("Open-Meteo request failed; no weather signal is available") from exc
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError) as exc:
        raise WeatherSignalError("Open-Meteo returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise WeatherSignalError("Open-Meteo returned an unexpected response")
    return payload


def classify_weather_code(code: int) -> str:
    """Map supported WMO weather codes to a small stable tag vocabulary."""
    if isinstance(code, bool) or not isinstance(code, int):
        raise WeatherDataError("weather_code must be an integer")
    if code == 0:
        return "clear"
    if code in {1, 2, 3}:
        return "cloudy"
    if code in {45, 48}:
        return "fog"
    if code in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}:
        return "rain"
    if code in {71, 73, 75, 77, 85, 86}:
        return "snow"
    if code in {95, 96, 97, 99}:
        return "storm"
    raise WeatherDataError(f"Unsupported WMO weather_code: {code}")


def fetch_city_weather(
    city: str,
    *,
    country_code: str | None = None,
    opener: _OPENER = urlopen,
) -> dict[str, str | int]:
    """Return current city-level weather metadata without persisting it.

    A country code is recommended for ambiguous city names. Geocoder results
    are filtered by exact city name and, when supplied, country code before
    deciding whether a result is unique.
    """
    city, country_code = _city_and_country(city, country_code)
    geo_params: dict[str, str | int] = {"name": city, "count": 10, "language": "en", "format": "json"}
    if country_code:
        geo_params["countryCode"] = country_code
    geocode = _read_json(f"{_GEOCODING_ENDPOINT}?{urlencode(geo_params)}", opener)
    results = geocode.get("results")
    if results is None:
        raise CityNotFoundError(f"No city found for {city!r}")
    if not isinstance(results, list):
        raise WeatherDataError("Geocoding response has invalid results")
    if not results:
        raise CityNotFoundError(f"No city found for {city!r}")
    if any(not isinstance(place, dict) for place in results):
        raise WeatherDataError("Geocoding response has an invalid city entry")
    matches = [
        place for place in results
        if isinstance(place.get("name"), str)
        and place["name"].strip().casefold() == city.casefold()
        and (country_code is None or
             isinstance(place.get("country_code"), str)
             and place["country_code"].upper() == country_code)
    ]
    if not matches:
        raise CityNotFoundError(f"No exact city match for {city!r}" +
                                (f" in {country_code}" if country_code else ""))
    if len(matches) > 1:
        regions = sorted({place.get("admin1", "") for place in matches
                          if isinstance(place.get("admin1"), str) and place.get("admin1", "").strip()})
        region_hint = f" (regions: {', '.join(regions)})" if regions else ""
        country_hint = f" in {country_code}" if country_code else "; provide country_code"
        raise AmbiguousCityError(f"Multiple exact city matches for {city!r}{country_hint}{region_hint}")
    place = matches[0]
    if not isinstance(place, dict):
        raise WeatherDataError("Geocoding response has an invalid city entry")
    name, country, returned_code = place.get("name"), place.get("country"), place.get("country_code")
    if not isinstance(name, str) or not name.strip() or not isinstance(country, str) or not country.strip():
        raise WeatherDataError("Geocoding response is missing the city or country name")
    if country_code and (not isinstance(returned_code, str) or returned_code.upper() != country_code):
        raise WeatherDataError("Geocoding response did not match the requested country code")
    latitude, longitude = place.get("latitude"), place.get("longitude")
    if (isinstance(latitude, bool) or not isinstance(latitude, (int, float)) or not math.isfinite(latitude)
            or not -90 <= latitude <= 90 or isinstance(longitude, bool)
            or not isinstance(longitude, (int, float)) or not math.isfinite(longitude)
            or not -180 <= longitude <= 180):
        raise WeatherDataError("Geocoding response has invalid coordinates")

    display_parts = [name.strip()]
    admin1 = place.get("admin1")
    if isinstance(admin1, str) and admin1.strip() and admin1.strip() not in display_parts:
        display_parts.append(admin1.strip())
    if country.strip() not in display_parts:
        display_parts.append(country.strip())
    display_city = ", ".join(display_parts)

    forecast_params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "weather_code",
        "timezone": "UTC",
    }
    forecast = _read_json(f"{_FORECAST_ENDPOINT}?{urlencode(forecast_params)}", opener)
    current = forecast.get("current")
    if not isinstance(current, dict):
        raise WeatherDataError("Forecast response is missing current weather")
    code, observed = current.get("weather_code"), current.get("time")
    tag = classify_weather_code(code)
    if not isinstance(observed, str):
        raise WeatherDataError("Forecast response is missing the observation time")
    try:
        observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WeatherDataError("Forecast response has an invalid observation time") from exc
    # The request explicitly pins the forecast timezone to UTC. Open-Meteo's
    # ISO timestamps may omit an offset in that case, so interpret a naive
    # timestamp as UTC and normalize any explicit offset the same way.
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    elif observed_at.utcoffset() is None:
        raise WeatherDataError("Forecast observation time has an invalid timezone")
    observed_at = observed_at.astimezone(timezone.utc).isoformat(timespec="seconds")
    return {
        "city": display_city,
        "tag": tag,
        "weather_code": code,
        "observed_at": observed_at,
        "source": "open-meteo",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch a city-level Open-Meteo weather tag")
    parser.add_argument("--city", required=True, help="City name, optionally followed by a country code")
    parser.add_argument("--country-code", help="Two-letter ISO country code, for example GB")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = fetch_city_weather(args.city, country_code=args.country_code)
    except WeatherSignalError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
