# Presenting Ambient Wallpapers

The project is a creative portfolio demonstration: visual quality first, followed by a clear example of feedback-led design, a straightforward way to try the skill and verifiable engineering claims.

## Source of truth

- The research-station images at `showcase/images/` are the real examples. Don't replace them with unrelated promotional renders.
- The GitHub README brand banner is `docs/assets/ambient-banner.svg`; the showcase remains a lightweight static page.
- Before-and-after visuals need actual earlier drafts. Until those are available, tell the story in words and show only verified final artwork.
- Avoid presenting untested native macOS functionality as hardware-verified.

## Prepare the GitHub social preview

The source-controlled generator builds a share card from **those same three images**. This avoids introducing different artwork or checking a binary marketing export into Git history.

```bash
python -m pip install Pillow
python tools/render_social_preview.py
```

The output is `dist/ambient-wallpapers-social-preview.jpg` at **1280 × 640**. The release-readiness workflow also attaches the generated file as a downloadable artifact.

To apply it to the repository, open **GitHub → Settings → General → Social preview**, then upload the generated JPG. This setting is not changed by commits or the GitHub Pages deployment.

## Final visitor review

1. Open the README signed out, on desktop and mobile. The branded banner and actual artwork should be visible without navigating to another page.
2. Follow **Explore the showcase** and the gallery. Check layout, text contrast, keyboard focus and loading behaviour.
3. Follow **Get the skill**, install it in a clean Codex session and verify the first prompt.
4. Confirm the platform limitations and release status remain accurate. Record an authentic short screen demo **only after a successful real install**; do not stage fake interactions.
5. Upload the social preview manually and check how the GitHub link looks when shared.

## Repository metadata

Suggested description: **AI-generated wallpapers shaped by your taste. One visual world, beautifully composed for every screen.**

Suggested topics: `codex`, `agent-skills`, `wallpapers`, `desktop-personalization`, `image-generation`, `windows`, `macos`.

These are repository settings, not source files; the maintainer must review and apply them through GitHub.
