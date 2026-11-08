# Ambient Wallpapers

**A Codex skill for a desktop that feels like yours.** Find a visual direction, generate a coordinated wallpaper collection for your displays, and refine it from feedback.

[Live showcase](https://maxlauriehutchinson.github.io/ambient-wallpapers/) · [Install in Codex](#install-in-codex) · [How it works](#how-it-works) · [GitHub Releases](https://github.com/MaxLaurieHutchinson/ambient-wallpapers/releases)

![Research-station wallpaper from the Ambient Wallpapers showcase](showcase/images/station-exterior.png)

> **Status:** public v0.1.0 release candidate. The skill, scripts and example assets exist; the tagged GitHub Release, selected licence and live multi-display installation verification are pending.

## Features

- **Preference calibration:** learn from feedback; distinguish confirmed taste from suggestions and rejected directions.
- **Coordinated imagery:** compose a consistent collection for a laptop and multiple displays, with honest source and output dimensions.
- **Windows backup/apply/restore:** inspect, plan, apply and verify wallpapers, preserving a rollback receipt.
- **Optional local signals:** choose among *approved cached images* using time, connected displays, opted-in city weather or data-only agent suggestions.
- **Portable output:** generate/export files on macOS and Linux; direct wallpaper application is currently supported on Windows only.

[See the three-screen research-station collection](https://maxlauriehutchinson.github.io/ambient-wallpapers/). The website is a static showcase, not a remotely controlled desktop.

## Install in Codex

**Requirements:** Codex with an image-generation tool; Python 3.10+ for the bundled helpers; [Pillow](https://pypi.org/project/Pillow/) for preparing images. Windows PowerShell is required only to inspect, apply or restore desktop wallpaper.

### Codex skill installer

Ask your installed `$skill-installer` to install this repository directory:

```text
https://github.com/MaxLaurieHutchinson/ambient-wallpapers/tree/main/skills/ambient-wallpapers
```

If the installer isn't present or your Codex build uses a different skill location, install manually.

### Manual installation

Copy **the whole** `skills/ambient-wallpapers` folder, including scripts, examples and references, into your Codex user-skills folder.

**macOS / Linux**

```bash
git clone --depth 1 https://github.com/MaxLaurieHutchinson/ambient-wallpapers.git
mkdir -p "$HOME/.agents/skills"
cp -R ambient-wallpapers/skills/ambient-wallpapers "$HOME/.agents/skills/"
```

**Windows PowerShell**

```powershell
git clone --depth 1 https://github.com/MaxLaurieHutchinson/ambient-wallpapers.git
New-Item -ItemType Directory -Force "$HOME/.agents/skills" | Out-Null
Copy-Item -Recurse -Force "ambient-wallpapers/skills/ambient-wallpapers" "$HOME/.agents/skills/"
```

The documented Codex user skill directory is `~/.agents/skills/`. Older Codex installers may use `~/.codex/skills/`; check your active skill list if it doesn't appear. Replace any previous installation deliberately rather than copying a second folder inside it.

Start a new Codex session and enter:

```text
$ambient-wallpapers make my desktop feel more like me
```

**Safe default:** the example profile ships with `enabled: false` and `allow_apply: false`. Generation/export is separate from applying a wallpaper or scheduling any task.

## How it works

1. **Calibrate:** propose a visual direction based on confirmed preferences and user feedback, not assumptions about interests.
2. **Generate:** produce a coherent set with a separate composition for each display.
3. **Prepare:** inspect true dimensions; opt in before upscaling; save original sources, outputs and a dimension manifest.
4. **Plan and apply:** on Windows, inspect displays, back up existing settings, plan assignments, apply, verify, and keep rollback data.
5. **Adapt (optional):** select from approved local packs using permitted time, display, city weather and agent categories. Manual choice takes precedence.

Agent inputs are **data only** and do not grant filesystem permissions or execute commands. Weather uses a city supplied by the user, not GPS. Scheduled generation requires the image tool and the local desktop runtime to be available when it runs.

Read the [skill instructions](skills/ambient-wallpapers/SKILL.md) and [implementation references](skills/ambient-wallpapers/references/) for behavioural contracts and supported adapters.

## Verify locally

```bash
python -m pip install Pillow
python -m unittest discover -s skills/ambient-wallpapers/tests -v
python tools/package_ambient_skill.py --version 0.1.0
python tools/verify_release.py
```

For Windows-specific **non-mutating** PowerShell contract tests:

```powershell
pwsh -NoProfile -File skills/ambient-wallpapers/tests/test_windows_roles.ps1
pwsh -NoProfile -File skills/ambient-wallpapers/tests/test_signal_task_plan.ps1
```

CI checks Python tests, Windows contracts, reproducible packages and full-history credential scanning. Automated tests don't replace a manual visual and rollback check on a real Windows machine.

## Distribution and boundaries

A tagged release will provide a portable skill ZIP, a showcase ZIP and SHA-256 manifest under [GitHub Releases](https://github.com/MaxLaurieHutchinson/ambient-wallpapers/releases). Generated archives are no longer committed to the source branch.

- **Upscaling doesn't create native image detail.** Output resolution is not generation resolution.
- **Desktop application is Windows-only** at present. Restoring a static image does not prove that Windows Spotlight rotation has resumed.
- **Weather, agent suggestions and schedules are opt-in.** A cloud task without desktop access cannot change local wallpaper.
- **No private profiles or display identifiers** should appear in the repository or shareable bundles.

[Contributing](CONTRIBUTING.md) · [Security policy](SECURITY.md) · [Maintainer release checklist](docs/RELEASING.md)

**Licensing pending:** public source visibility alone grants no reuse rights. The maintainer must choose a code licence and confirm separate artwork rights before publishing a tagged release.
