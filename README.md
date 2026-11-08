# Ambient Wallpapers

A reusable Codex skill for a desktop that fits its owner: learn from relevant history, confirm a visual direction, generate a coordinated collection, and refine it from what the user actually likes.

[Open the showcase](showcase/index.html) to see the research-station collection across a laptop and two displays.

## Use it

Install the `ambient-wallpapers` folder from the skill archive in your Codex skills directory, then invoke:

```text
$ambient-wallpapers make my desktop feel more like me
```

The skill supports preference calibration, image generation, honest display sizing, a Windows backup/apply/restore adapter, local context selection, city-level weather and a data-only handoff for other agents. It exports files on platforms without a supported apply adapter.

Fresh generation and cached rotation are separate jobs. A schedule creates new art; a local signal job chooses authorized saved images. Weather uses a city supplied by the user, with an hourly cache and no GPS. Other agents can suggest an authorized pack or a future creative brief; they cannot use that handoff to grant permissions or run commands.

Manual choice takes priority. Schedules and signal sources are explicit opt-ins. Scheduled generation still depends on the local app, image tool and OS permissions being available.

## Shareable artifacts

- `dist/ambient-wallpapers-0.1.0.zip`: portable skill, scripts, generic example and tests.
- `dist/ambient-wallpapers-showcase-0.1.0.zip`: standalone gallery with local images.
- `dist/ambient-wallpapers-manifest.json`: file and archive hashes.

The repository and archives exclude private preference profiles, display identifiers, local account paths and execution receipts. The showcase can be opened locally; it has not been deployed to a website.

## Validation

Run the Python suite with a Python environment containing Pillow:

```text
python -m unittest discover -s skills/ambient-wallpapers/tests -v
```

The PowerShell contract checks exercise role mapping and task-action planning without changing Windows. Live application and scheduling receipts stay under `private/`, outside the shareable skill.
