---
name: ambient-wallpapers
description: Use when a user wants desktop wallpapers that fit their taste, coordinated monitor backgrounds, recurring wallpaper refreshes, or backgrounds that respond to time and connected displays.
---

# Ambient Wallpapers

Turn a user's visual preferences into a coordinated desktop. Learn from what they actually like on screen; treat interests and occupations as suggestions to explore.

## Find the direction

Read the current request and a small amount of relevant history or memory. Build a short, editable preference sketch with **confirmed**, **inferred**, and **rejected** entries, each with its source. Follow [preferences.md](references/preferences.md) when creating or updating that sketch. Keep personal evidence in a local user profile, outside this skill and any shareable bundle.

Before the first generation, state the proposed visual direction and ask one useful calibration question. Offer two or three distinct directions when seeing the difference would help. A user's interest in robotics can inspire a proposal; it does not establish that they want robots on their desktop. If the user already approved a concrete direction, continue without asking again. Preserve their latest feedback over earlier guesses.

Check connected displays, aspect ratios and pixel dimensions. Record disconnected displays as intended targets. For Windows, run `powershell -NoProfile -File scripts/windows_wallpaper.ps1 -Mode Inspect`. For macOS, read [macos.md](references/macos.md) and run `swift scripts/macos_wallpaper.swift --mode Inspect` in an authorised logged-in desktop session. On Linux, export images only.

## Make and apply the set

Use the available image-generation tool and its imagegen guidance. Describe one coherent art direction and a suitable composition for each display. Keep useful space for icons and taskbars. Review the images before applying them.

Inspect actual generated dimensions. Ask before local upscaling unless the user already chose it; call upscaled files upscaled. Preserve generated sources, final files, prompts and a dimension manifest. Use `python scripts/prepare_images.py --help` for the local preparation helper (Pillow required). A 4K request in a prompt is not proof of a 4K source.

For Windows application, read [windows.md](references/windows.md). For macOS static-image application, read [macos.md](references/macos.md). Both adapters support Inspect, Plan, Apply and Restore and preserve backups and a rollback receipt. Plan the assignments first; apply only within the user's authorized scope. Recheck the saved wallpaper and report which displays were actually configured. macOS dynamic wallpaper and multi-Space restoration is not guaranteed. Keep previous sets available for rollback.

Record brief visual feedback: what to keep, what missed, and the next change. Technical success and visual approval are separate results.

## Recurring and responsive modes

Read [automation.md](references/automation.md) when the user requests daily/weekly refreshes or contextual changes. Scheduled **generation** makes new art; signal-driven **selection** chooses an already approved cached set. Confirm cadence, timezone and recurring application scope before activation.

The local runner, `python scripts/ambient.py`, supports `plan` and `apply`; use `--help` for arguments. Its profile is described in [profile.md](references/profile.md). Supported context includes time of day, connected displays, an opted-in city weather category and allowlisted agent suggestions. Read [context.md](references/context.md) for weather and Dot/agent handoffs. Leave recurring work disabled when the user is only exploring the idea.

Finish with the applied/exported files, actual image sizes, rollback location and the true scheduling state. Keep private profiles out of demos and packages.
