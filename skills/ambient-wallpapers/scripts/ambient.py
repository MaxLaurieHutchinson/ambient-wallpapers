"""Select already approved wallpaper packs from local display and time signals."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


class ProfileError(ValueError):
    """The profile or one of its referenced assets is unsafe or invalid."""


Adapter = Callable[[Mapping[str, Any]], Mapping[str, Any]]
WEATHER_TAGS = frozenset({"clear", "cloudy", "rain", "snow", "fog", "storm"})
SIGNAL_NAMES = frozenset({"time_of_day", "display_count", "weather", "agent"})


def _utc_now(value: datetime | None = None) -> datetime:
    current = value or datetime.now().astimezone()
    if current.tzinfo is None:
        raise ProfileError("The planner requires a timezone-aware local time.")
    return current.astimezone(timezone.utc)


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProfileError(f"{field} must be an ISO 8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ProfileError(f"{field} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _profile_root(profile: Mapping[str, Any]) -> Path:
    root = profile.get("asset_root")
    if not isinstance(root, str) or not root.strip():
        raise ProfileError("asset_root must be a directory path.")
    resolved = Path(root).expanduser().resolve()
    if not resolved.is_dir():
        raise ProfileError(f"asset_root does not exist: {resolved}")
    return resolved


def _image_path(root: Path, value: Any, pack_id: str, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"Pack '{pack_id}' needs an image path for {field}.")
    supplied = Path(value)
    resolved = (root / supplied).resolve() if not supplied.is_absolute() else supplied.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProfileError(f"Pack '{pack_id}' {field} path escapes asset_root.") from exc
    if resolved.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ProfileError(f"Pack '{pack_id}' {field} is not a supported image file.")
    if not resolved.is_file():
        raise ProfileError(f"Pack '{pack_id}' {field} image is missing: {resolved}")
    return resolved


@dataclass(frozen=True)
class ValidatedProfile:
    raw: Mapping[str, Any]
    root: Path
    packs: Mapping[str, Mapping[str, Any]]
    signals: frozenset[str]
    fallback: str
    display_roles: Mapping[str, str]


def validate_profile(profile: Mapping[str, Any]) -> ValidatedProfile:
    if not isinstance(profile, Mapping) or profile.get("version") != 1:
        raise ProfileError("Profile must be a JSON object with version 1.")
    root = _profile_root(profile)
    signals_obj = profile.get("signals", {})
    if not isinstance(signals_obj, Mapping):
        raise ProfileError("signals must be a JSON object.")
    allowed = signals_obj.get("allowed", [])
    if not isinstance(allowed, list) or any(x not in SIGNAL_NAMES for x in allowed):
        raise ProfileError("signals.allowed may contain time_of_day, display_count, weather, and agent.")
    day_start = signals_obj.get("day_start", 7)
    night_start = signals_obj.get("night_start", 19)
    cooldown = signals_obj.get("min_interval_minutes", 30)
    if (type(day_start) is not int or type(night_start) is not int or
            not 0 <= day_start < night_start <= 23):
        raise ProfileError("day_start and night_start must be hours with 0 <= day_start < night_start <= 23.")
    if type(cooldown) is not int or cooldown < 0:
        raise ProfileError("min_interval_minutes must be a nonnegative integer.")

    entries = profile.get("catalog")
    if not isinstance(entries, list):
        raise ProfileError("catalog must be a list of wallpaper packs.")
    approved: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ProfileError("Each catalog entry must be an object.")
        if entry.get("approved") is not True:
            continue
        pack_id = entry.get("id")
        if not isinstance(pack_id, str) or not pack_id.strip():
            raise ProfileError("Approved packs need a nonempty string id.")
        if pack_id in approved:
            raise ProfileError(f"Duplicate wallpaper pack id: {pack_id}")
        tags = entry.get("tags", [])
        if not isinstance(tags, list) or any(tag not in {"day", "night", "mobile", "docked", *WEATHER_TAGS} for tag in tags):
            raise ProfileError(f"Pack '{pack_id}' has an unsupported tag.")
        _image_path(root, entry.get("laptop"), pack_id, "laptop")
        monitors = entry.get("monitors", [])
        if not isinstance(monitors, list):
            raise ProfileError(f"Pack '{pack_id}' monitors must be a list.")
        for index, item in enumerate(monitors):
            _image_path(root, item, pack_id, f"monitor {index + 1}")
        approved[pack_id] = entry

    fallback = profile.get("fallback_pack")
    if not isinstance(fallback, str) or fallback not in approved:
        raise ProfileError("fallback_pack must name an approved pack.")
    override = profile.get("manual_override")
    if override is not None:
        if not isinstance(override, Mapping):
            raise ProfileError("manual_override must be an object or null.")
        if override.get("pack_id") not in approved:
            raise ProfileError("manual_override must name an approved pack.")
        _parse_time(override.get("until"), "manual_override.until")
    if type(profile.get("enabled", False)) is not bool:
        raise ProfileError("enabled must be true or false.")
    if type(profile.get("allow_apply", False)) is not bool:
        raise ProfileError("allow_apply must be true or false.")
    roles = profile.get("display_roles", {})
    if not isinstance(roles, Mapping) or any(
            not isinstance(device_id, str) or not device_id.strip() or
            not isinstance(role, str) or role not in {"laptop", "monitor"}
            for device_id, role in roles.items()):
        raise ProfileError("display_roles must map nonempty device IDs to laptop or monitor.")
    sources = profile.get("context_sources", {})
    if not isinstance(sources, Mapping):
        raise ProfileError("context_sources must map weather and agent to source allowlists.")
    for name, values in sources.items():
        if name not in {"weather", "agent"} or not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip() for value in values):
            raise ProfileError("context_sources must contain weather and/or agent lists of nonempty source names.")
    inbox = profile.get("signal_inbox")
    if inbox is not None and (not isinstance(inbox, str) or not inbox.strip()):
        raise ProfileError("signal_inbox must be a nonempty path when configured.")
    return ValidatedProfile(profile, root, approved, frozenset(allowed), fallback, dict(roles))


def _assignments(entry: Mapping[str, Any], root: Path,
                 display_roles: Mapping[str, str], display_count: int) -> dict[str, Any]:
    laptop = _image_path(root, entry.get("laptop"), str(entry["id"]), "laptop")
    external = [_image_path(root, path, str(entry["id"]), f"monitor {i + 1}")
                for i, path in enumerate(entry.get("monitors", []))]
    if display_count > 1 and not external:
        raise ProfileError(f"Pack '{entry['id']}' has no images for the connected external displays.")
    return {"laptop": str(laptop), "monitors": [str(path) for path in external],
            "display_roles": dict(display_roles)}


def _read_previous(state: Mapping[str, Any] | None) -> tuple[str | None, datetime | None, int | None, list[str] | None]:
    if state is None:
        return None, None, None, None
    if not isinstance(state, Mapping):
        raise ProfileError("state must be a JSON object.")
    previous_id = state.get("pack_id")
    timestamp = state.get("applied_at")
    previous_count = state.get("display_count")
    previous_displays = state.get("display_ids")
    if not isinstance(previous_displays, list) or any(not isinstance(item, str) for item in previous_displays):
        previous_displays = None
    if timestamp is None:
        return previous_id, None, previous_count, previous_displays
    return previous_id, _parse_time(timestamp, "state.applied_at"), previous_count, previous_displays


def build_plan(profile: Mapping[str, Any], *, hour: int | None = None,
               display_count: int = 1, now: datetime | None = None,
               state: Mapping[str, Any] | None = None,
               context: Mapping[str, Any] | None = None,
               display_ids: list[str] | None = None) -> dict[str, Any]:
    validated = validate_profile(profile)
    if type(display_count) is not int or display_count < 1:
        raise ProfileError("display_count must be a positive integer.")
    if display_ids is not None and (
            not isinstance(display_ids, list) or any(not isinstance(item, str) or not item for item in display_ids)
            or len(display_ids) != len(set(display_ids))):
        raise ProfileError("display_ids must be unique nonempty display identifiers.")
    stable_display_ids = sorted(display_ids) if display_ids is not None else None
    current = _utc_now(now)
    local_hour = current.astimezone().hour if hour is None else hour
    if type(local_hour) is not int or not 0 <= local_hour <= 23:
        raise ProfileError("hour must be an integer from 0 to 23.")
    if not validated.raw.get("enabled", False):
        return {"status": "DISABLED", "reason": "Wallpaper signals are not enabled."}

    signals = validated.raw.get("signals", {})
    required: set[str] = set()
    if "time_of_day" in validated.signals:
        required.add("night" if local_hour >= signals.get("night_start", 19) or
                     local_hour < signals.get("day_start", 7) else "day")
    if "display_count" in validated.signals:
        required.add("docked" if display_count > 1 else "mobile")

    context = context if isinstance(context, Mapping) else {}
    reasons: list[str] = []
    if "weather" in validated.signals:
        weather = context.get("weather")
        weather_tags = weather.get("tags", []) if isinstance(weather, Mapping) else []
        if isinstance(weather_tags, list):
            valid_tags = [tag for tag in weather_tags if isinstance(tag, str) and tag in WEATHER_TAGS]
            required.update(valid_tags)
            if valid_tags:
                reasons.append(f"Cached weather context added: {', '.join(sorted(set(valid_tags)))}.")
        else:
            reasons.append("Weather context was malformed and ignored.")

    override = validated.raw.get("manual_override")
    manual_live = override is not None and _parse_time(override["until"], "manual_override.until") > current
    if manual_live:
        selected = validated.packs[override["pack_id"]]
        reason = f"Manual override remains active until {override['until']}."
    else:
        agent = context.get("agent") if "agent" in validated.signals else None
        preferred = agent.get("preferred_pack") if isinstance(agent, Mapping) else None
        if isinstance(preferred, str) and preferred in validated.packs:
            selected = validated.packs[preferred]
            reason = f"Agent context preferred approved cached pack '{preferred}'."
        else:
            if preferred is not None:
                reasons.append(f"Agent preferred-pack hint '{preferred}' was unknown or unapproved and ignored.")
            matches = ([entry for entry in validated.packs.values()
                        if required.issubset(set(entry.get("tags", [])))] if required else [])
            selected = matches[0] if matches else validated.packs[validated.fallback]
            reason = ("Approved cached pack matches the enabled signals."
                      if matches else "No approved pack matches every enabled signal; using fallback_pack.")
    if reasons:
        reason = " ".join([reason, *reasons])

    pack_id = str(selected["id"])
    previous_id, applied_at, previous_count, previous_displays = _read_previous(state)
    status = "READY"
    same_topology = stable_display_ids is None or previous_displays == stable_display_ids
    if previous_id == pack_id and previous_count == display_count and same_topology:
        status = "UNCHANGED"
        reason = "This approved pack is already assigned to the current display count."
    else:
        cooldown = signals.get("min_interval_minutes", 30)
        if not manual_live and applied_at is not None and (current - applied_at).total_seconds() < cooldown * 60:
            status = "COOLDOWN"
            reason = f"A wallpaper change occurred within the {cooldown}-minute minimum interval."
    return {
        "status": status,
        "pack_id": pack_id,
        "display_count": display_count,
        "display_ids": stable_display_ids,
        "signals": sorted(required),
        "reason": reason,
        "assignments": _assignments(selected, validated.root, validated.display_roles, display_count),
    }


def load_profile(path: str | Path) -> tuple[dict[str, Any], Path]:
    profile_path = Path(path).expanduser().resolve()
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileError(f"Cannot read profile: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Profile is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError("Profile root must be a JSON object.")
    if not isinstance(data.get("asset_root"), str):
        data["asset_root"] = str(profile_path.parent)
    elif not Path(data["asset_root"]).is_absolute():
        data["asset_root"] = str((profile_path.parent / data["asset_root"]).resolve())
    if isinstance(data.get("signal_inbox"), str) and not Path(data["signal_inbox"]).is_absolute():
        data["signal_inbox"] = str((profile_path.parent / data["signal_inbox"]).resolve())
    return data, profile_path


def _read_signal_context(profile: Mapping[str, Any], *, now: datetime | None = None) -> Mapping[str, Any]:
    inbox = profile.get("signal_inbox")
    if not isinstance(inbox, str) or not inbox.strip():
        return {}
    inbox_path = Path(inbox).expanduser().resolve()
    if not inbox_path.is_file():
        return {}
    sources = profile.get("context_sources", {})
    allowed_sources = {
        name: list(values) for name, values in sources.items()
        if name in {"weather", "agent"} and isinstance(values, list)
    } if isinstance(sources, Mapping) else {}
    try:
        try:
            from context_signals import read_signals
        except ModuleNotFoundError as exc:
            if exc.name == "context_signals":
                return {}
            raise
        events = read_signals(inbox_path, now=_utc_now(now), allowed_sources=allowed_sources)
    except (OSError, ValueError, TypeError) as exc:
        raise ProfileError(f"Cannot read cached context signals: {exc}") from exc
    if not isinstance(events, Mapping):
        raise ProfileError("Cached context reader returned an invalid result.")
    return events


def _read_state(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"Cannot read the previous apply state: {exc}") from exc
    if not isinstance(value, dict):
        raise ProfileError("The previous apply state must be a JSON object.")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=path.name + ".",
                                         suffix=".tmp", delete=False) as handle:
            temp_path = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _powershell_executable() -> str:
    for executable in ("pwsh.exe", "powershell.exe", "pwsh"):
        resolved = shutil.which(executable)
        if resolved:
            return resolved
    raise ProfileError("PowerShell was not found. Windows apply requires pwsh or Windows PowerShell.")


def _decode_adapter(stdout: str, operation: str) -> Mapping[str, Any]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Wallpaper helper returned invalid JSON during {operation}.") from exc
    if not isinstance(value, Mapping):
        raise ProfileError(f"Wallpaper helper returned an unexpected result during {operation}.")
    return value


def _call_windows(script: Path, mode: str, *, assignment: Mapping[str, Any] | None = None,
                  backup_root: Path | None = None) -> Mapping[str, Any]:
    if not script.is_file():
        raise ProfileError(f"Windows wallpaper adapter is missing: {script}")
    with tempfile.TemporaryDirectory(prefix="ambient-wallpapers-") as temp_dir:
        command = [_powershell_executable(), "-NoProfile", "-File", str(script), "-Mode", mode]
        if assignment is not None:
            assignment_path = Path(temp_dir) / "assignment.json"
            assignment_path.write_text(json.dumps(assignment), encoding="utf-8")
            command.extend(["-AssignmentPath", str(assignment_path)])
        if backup_root is not None:
            command.extend(["-BackupRoot", str(backup_root.resolve())])
        try:
            completed = subprocess.run(command, shell=False, capture_output=True, text=True,
                                       encoding="utf-8", timeout=90,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProfileError(f"Wallpaper helper could not finish {mode}: {exc}") from exc
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
            raise ProfileError(f"Wallpaper helper failed during {mode}: {message}")
        return _decode_adapter(completed.stdout, mode)


def inspect_connected_displays(script: Path) -> list[str]:
    result = _call_windows(script, "Inspect")
    monitors = result.get("Monitors")
    if not isinstance(monitors, list):
        raise ProfileError("Inspect did not return a monitor list.")
    connected = [monitor for monitor in monitors if isinstance(monitor, Mapping) and
                 monitor.get("Connected") is True]
    if not connected:
        raise ProfileError("Inspect returned no connected displays; refusing wallpaper changes.")
    identifiers = [monitor.get("DevicePath") for monitor in connected]
    if any(not isinstance(item, str) or not item for item in identifiers):
        raise ProfileError("Inspect returned a connected display without a device identifier.")
    return sorted(identifiers)


def inspect_display_count(script: Path) -> int:
    return len(inspect_connected_displays(script))


def windows_apply(script: Path, assignment: Mapping[str, Any], backup_root: Path) -> Mapping[str, Any]:
    planned = _call_windows(script, "Plan", assignment=assignment)
    if planned.get("Result") != "Planned":
        return {"verified": False, "result": "Plan did not return a read-only assignment", "detail": planned}
    expected = _assignment_signature(planned.get("Assignment"))
    if expected is None:
        return {"verified": False, "result": "Plan returned malformed assignments", "detail": planned}
    result = _call_windows(script, "Apply", assignment=assignment, backup_root=backup_root)
    if result.get("Result") != "Applied":
        return {"verified": False, "result": result.get("Result", "Unknown"),
                "detail": {"plan": planned, "apply": result}}
    actual = _assignment_signature(result.get("Assignment"))
    if actual != expected:
        return {"verified": False, "result": "Apply assignments differed from the read-only plan",
                "detail": {"plan": planned, "apply": result}}
    return {"verified": True, "result": "Applied", "detail": {"plan": planned, "apply": result}}


def _assignment_signature(assignments: Any) -> dict[str, str] | None:
    if not isinstance(assignments, list) or not assignments:
        return None
    signature: dict[str, str] = {}
    for item in assignments:
        if not isinstance(item, Mapping):
            return None
        device_id = item.get("DevicePath")
        image_path = item.get("WallpaperPath")
        if not isinstance(device_id, str) or not device_id or not isinstance(image_path, str) or not image_path:
            return None
        if device_id in signature:
            return None
        signature[device_id] = image_path
    return signature


def apply_profile(profile: Mapping[str, Any], *, state_path: str | Path,
                  adapter: Adapter | None = None, hour: int | None = None,
                  display_count: int | None = None,
                  now: datetime | None = None,
                  context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    validated = validate_profile(profile)
    if validated.raw.get("enabled") is not True:
        raise ProfileError("Apply is disabled until the profile is enabled.")
    if validated.raw.get("allow_apply") is not True:
        raise ProfileError("Apply requires explicit allow_apply: true in the profile.")
    script = Path(__file__).with_name("windows_wallpaper.ps1")
    try:
        connected_ids: list[str] | None = None
        if adapter is None:
            if os.name != "nt":
                raise ProfileError("Wallpaper apply is currently supported on Windows only.")
            connected_ids = inspect_connected_displays(script)
            connected_count = len(connected_ids)
        else:
            connected_count = 1 if display_count is None else display_count
        state_file = Path(state_path).expanduser().resolve()
        signal_context = context if context is not None else _read_signal_context(profile, now=now)
        plan = build_plan(profile, hour=hour, display_count=connected_count,
                          now=now, state=_read_state(state_file), context=signal_context,
                          display_ids=connected_ids)
        if plan["status"] != "READY":
            return {**plan, "status": plan["status"]}
        outcome = adapter(plan["assignments"]) if adapter is not None else windows_apply(
            script, plan["assignments"], validated.root.parent / "backup")
        if not isinstance(outcome, Mapping) or outcome.get("verified") is not True:
            return {**plan, "status": "APPLY_FAILED",
                    "detail": dict(outcome) if isinstance(outcome, Mapping) else "No verified adapter result."}
        applied_at = _utc_now(now).isoformat()
        saved = {"pack_id": plan["pack_id"], "display_count": connected_count,
                 "applied_at": applied_at,
                 "assignments": plan["assignments"],
                 "adapter_result": outcome.get("result", "Applied")}
        if connected_ids is not None:
            saved["display_ids"] = sorted(connected_ids)
        receipt = outcome.get("detail")
        if isinstance(receipt, Mapping):
            saved["adapter_receipt"] = receipt
            applied = receipt.get("apply")
            if isinstance(applied, Mapping) and isinstance(applied.get("StatePath"), str):
                saved["restore_state_path"] = applied["StatePath"]
        _atomic_json(state_file, saved)
        return {**plan, "status": "APPLIED", "applied_at": applied_at,
                "adapter_result": outcome}
    except ProfileError:
        raise
    except Exception as exc:
        return {"status": "APPLY_FAILED", "detail": str(exc)}


def _emit(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply"):
        command = commands.add_parser(name)
        command.add_argument("--profile", required=True, type=Path)
        command.add_argument("--state", type=Path,
                             help="Apply-state JSON path; defaults beside the profile.")
        if name == "plan":
            command.add_argument("--hour", type=int, help="Local-hour fixture 0 to 23.")
            command.add_argument("--display-count", type=int, default=1,
                                 help="Connected-screen count for a read-only plan.")
    args = parser.parse_args(argv)
    try:
        profile, profile_path = load_profile(args.profile)
        state_path = args.state or profile_path.with_name(profile_path.stem + ".state.json")
        if args.command == "plan":
            state = _read_state(state_path)
            context = _read_signal_context(profile)
            _emit(build_plan(profile, hour=args.hour, display_count=args.display_count,
                             state=state, context=context))
            return 0
        if sys.platform != "win32":
            raise ProfileError("Apply is supported on Windows only; plan works on other systems.")
        result = apply_profile(profile, state_path=state_path)
        _emit(result)
        return 1 if result.get("status") == "APPLY_FAILED" else 0
    except ProfileError as exc:
        print(f"ambient-wallpapers: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
