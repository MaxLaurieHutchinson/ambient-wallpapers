# Public-release playbook

This is a **maintainer checklist**. Opening or merging a PR does not itself authorise a release, credential rotation, history rewrite, public licensing decision or a user-machine task installation.

## Hard gates

- [x] **Select licence structure.** The code and documentation use [MIT](../LICENSE); the six listed example images use [CC BY 4.0](../ASSETS-LICENSE.md) for rights the maintainer can license. Both notices are bundled with release archives.
- [x] **Record example-artwork origin.** The maintainer confirms that the three research-station artworks (reproduced at six paths) were generated with Codex for Ambient Wallpapers. This origin question is resolved; no separate provenance audit is a release prerequisite. If independently sourced references or third-party material are added later, review their rights before redistribution. The CC BY 4.0 notice grants only rights legally held.
- [ ] **Audit Git history and public artefacts.** Check older commits, Action logs, generated ZIPs, embedded metadata and demos. Rotate exposed credentials; deleting their latest occurrence is insufficient.
- [ ] **Run CI.** Python matrix, Windows contract checks, deterministic ZIP generation and the Gitleaks history scan must all pass.
- [ ] **Test actual Windows and macOS application.** With owner authorisation, inspect, plan, apply, verify and restore on real multi-display machines. Confirm saved backups and the Windows Spotlight/macOS dynamic wallpaper limitations. A macOS compile check is not live application evidence.
- [ ] **Review claims.** Use actual PNG pixel dimensions; describe upscaled files honestly. Distinguish running schedules from merely configured schedules.
- [ ] **Check first-time user experience.** Verify install in a clean Codex session, site navigation and gallery on mobile, metadata and sharing card.
- [ ] **Configure repository settings.** Enable default branch protection/rulesets, security alerts, CodeQL default setup, and private vulnerability reporting where available.

## Manual GitHub configuration

The connected file-editing API cannot change these settings, so the owner must do so in the GitHub UI:

- **Topics:** `codex`, `agent-skills`, `wallpapers`, `desktop-personalization`, `windows`, `macos`, `python`, `image-generation`.
- **Homepage:** `https://maxlauriehutchinson.github.io/ambient-wallpapers/`.
- **Social preview:** upload a suitably licensed wide screenshot.
- **Ruleset/branch protection:** protect `main` and require the actual successful CI check names before merging; disable force pushes.
- **Security:** enable CodeQL default setup, secret scanning/push protection and vulnerability reporting where available.

## Build and publish v0.1.0

From a clean checkout, with Python and Pillow installed:

```bash
python -m pip install Pillow
python -m unittest discover -s skills/ambient-wallpapers/tests -v
python tools/package_ambient_skill.py --version 0.1.0
python tools/verify_release.py
```

The builder creates deterministic, ignored `dist/` archives. Verification compares archives byte-for-byte with the source and against the manifest's hashes. It does not test real wallpaper mutation.

**Once the remaining manual release checks are closed**, review both committed licence notices, merge the PR, tag the reviewed latest `main` commit `v0.1.0`, and push the tag. The workflow reruns tests, refuses non-main tags or missing licensing, rebuilds and checks ZIPs, and publishes a GitHub Release.

After publication, download the release as a signed-out visitor, verify checksums, follow the site-to-GitHub install path, install in a fresh Codex session and confirm that the public claims reflect the supported platforms.
