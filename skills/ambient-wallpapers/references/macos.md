# macOS wallpaper support

The macOS adapter is native Swift using AppKit's NSWorkspace wallpaper API and CoreGraphics display discovery. It supports **Inspect, Plan, Apply and Restore** for static, file-backed wallpapers. It does **not** require an Electron app or AppleScript automation of System Settings.

## Prerequisites and boundaries

- A logged-in macOS desktop session with access to the displays being changed.
- Xcode Command Line Tools providing the `swift` executable.
- Python 3.10+ for the cached-pack runner. Pillow is required only for image preparation.
- Valid local static wallpapers, with an existing file-backed image for **every** connected screen if using Apply.

The adapter intentionally refuses to apply when an existing wallpaper cannot be backed up as a static image. macOS dynamic/video wallpapers, multiple Spaces, rotating wallpaper schedules and wallpapers on a disconnected display cannot be guaranteed to round-trip via AppKit. Report these limitations before allowing mutation; a user may prefer a manual wallpaper export instead.

The machine and any actual wallpaper settings are never mutated by Inspect or Plan. The actual appearance of an image and individual macOS Spaces require manual visual verification after Apply.

## Inspect displays, then plan

Use the bundled Swift adapter (from inside the installed skill directory):

```bash
swift scripts/macos_wallpaper.swift --mode Inspect
```

Each connected display is reported with its numeric CoreGraphics ID, whether it is built in, its actual dimensions and its name.

Create an assignment JSON with **absolute local file paths**:

```json
{
  "laptop": "/absolute/path/to/laptop.png",
  "monitors": ["/absolute/path/to/left.png", "/absolute/path/to/right.png"],
  "display_roles": {}
}
```

The bundled adapter maps the built-in display to `laptop` and external displays to `monitors`, from left to right by desktop coordinates. For unusual display arrangements, override roles with device IDs from Inspect. Display IDs and assignments are private machine state: never commit them.

```bash
swift scripts/macos_wallpaper.swift --mode Plan --assignment-path /absolute/private/assignments.json
```

Plan validates every image, every connected display and the assignment count. It returns a `PlanID` token binding image paths, roles, screen identities and dimensions. Review the proposed plan before invoking Apply.

## Apply with explicit approval

The Codex skill uses the existing `ambient.py` runner, which requires both `enabled=true` and `allow_apply=true` in a **private** profile and performs Plan before Apply.

For a direct, explicitly authorised application:

```bash
swift scripts/macos_wallpaper.swift --mode Apply \
  --assignment-path /absolute/private/assignments.json \
  --plan-id THE_PLAN_ID_RETURNED_ABOVE \
  --backup-root /absolute/private/ambient-wallpapers-backups
```

Apply checks that the plan token still matches. Before modifying **any** display, it copies every existing file-backed wallpaper into a private receipt directory and records scaling options and a JSON restore receipt. After setting all images, it reads them back. A failed apply attempts to restore the original static images and reports incomplete rollback explicitly.

Keep the receipt and copied originals. Do not delete them while rollback might be needed.

## Restore

```bash
swift scripts/macos_wallpaper.swift --mode Restore \
  --state-path /absolute/private/ambient-wallpapers-backups/RECEIPT/state.json
```

Restore checks all saved displays are currently connected and all backups are usable **before changing anything**. It restores the backed-up static image bytes and recorded scaling options, verifies the reported paths and reports that dynamic wallpapers and Space-specific state may still require manual restoration.

## Tests

Python unit tests simulate macOS bridge contracts without touching the host desktop. The GitHub `macos-latest` workflow checks Swift compilation and runs read-only protocol checks. A **real, authorised macOS multi-monitor exercise** is still required before calling live Apply/Restore production-verified. Do not enable unattended Mac wallpaper mutation until that is complete.

Fresh generation and recurring **selection** are separate workflows. The current bundled recurring-task installer is Windows Task Scheduler only; it does not install a macOS LaunchAgent. Scheduling on macOS remains a separate future capability.
