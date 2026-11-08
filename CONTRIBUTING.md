# Contributing

Ambient Wallpapers is an early public Codex skill. Keep contributions small, demonstrable and compatible with its user-authority boundaries.

## Before you submit

1. Explain the user need, change in behaviour and any platform assumptions.
2. Never commit private preference records, local paths, display IDs, backup images, receipts, credentials or unauthorised art.
3. Keep visual approval, desktop-application permission and technical verification separate. No silent location access, scheduling or model spend.
4. Document supported platforms accurately. A Windows implementation isn't evidence of macOS/Linux support.
5. Update relevant references and tests whenever a behavioural contract changes.

## Development checks

Use Python 3.10+ with Pillow:

```bash
python -m pip install Pillow
python -m unittest discover -s skills/ambient-wallpapers/tests -v
python tools/package_ambient_skill.py
python tools/verify_release.py
```

On Windows, also run the non-mutating PowerShell tests in the [README](README.md#verify-locally).

Describe test evidence, expected failure behaviour, rollback implications and any permission changes in your PR. Include screenshots for visual changes, without exposing personal wallpaper content.

## Licensing

The maintainer has not yet chosen and published a reusable code/artwork licence. External contributions and releases must wait until the licensing decision is made. Do not assume the public repository authorises redistribution.
