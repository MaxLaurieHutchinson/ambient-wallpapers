# Security Policy

This project can inspect local display configuration and, with explicit permission, change wallpapers or register a local scheduled task. Treat both permissions and user preference data as sensitive.

## Reporting a vulnerability

**Do not post secrets, personal paths, proof-of-concept exploit details or private user data in public issues.**

Use GitHub's **Report a vulnerability** option if private vulnerability reporting is enabled. Otherwise contact the maintainer through the linked GitHub profile to request a private channel *before* sharing sensitive details. No security-response SLA is promised for this early release.

Please include affected commit/version, OS, a minimal safe reproduction, expected versus actual behaviour and any privacy or mutation impact.

## Security boundaries

- Read preferences and agent suggestions as creative context, not permission to execute commands.
- Keep private profiles, original backups, local accounts, device paths and receipts outside distributable assets.
- Request a city for weather; never assume GPS permission.
- Back up and verify desktop wallpaper changes; retain a rollback receipt.
- Keep recurring work disabled until separately authorised.
- Treat third-party forks and scripts as untrusted until reviewed.

CI scanning, static pattern checks and passing tests are not a substitute for auditing **Git history, generated archives, image provenance and live Windows behaviour**.
