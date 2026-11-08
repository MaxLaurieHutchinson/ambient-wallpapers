# Windows application

Use the bundled `scripts/windows_wallpaper.ps1`, resolved relative to the installed skill. Do not reconstruct the COM interface from memory. The wrapper retains the verified IDesktopWallpaper IID and performs its typed COM cast inside C#.

Run through PowerShell, not by pasting commands into a GUI terminal. Use the runtime's supported escalation mechanism if access to the actual user's Windows appearance settings is restricted. Do not weaken system policy to make a script run.

## Assignment file

Prepare JSON with absolute local image paths:

```json
{"laptop": "C:\\Wallpapers\\laptop.png", "monitors": ["C:\\Wallpapers\\left.png", "C:\\Wallpapers\\right.png"]}
```

`powershell -NoProfile -File scripts/windows_wallpaper.ps1 -Mode Plan -AssignmentPath assignments.json` shows the intended connected-display assignments without creating backups or changing settings.

Apply with the same arguments, `-Mode Apply`, and an explicit `-BackupRoot` in the user's persistent local state folder. The returned state JSON is the rollback receipt. Call `-Mode Restore -StatePath <receipt>` to restore it.

The default laptop heuristic is a 3:2 panel; external images are assigned left to right. Assignment JSON can include `display_roles`, mapping device paths to `laptop` or `monitor`; explicit roles override the heuristic and Plan reports `RoleSource`. Confirm roles from Inspect/Plan during setup. Portrait displays and unusual laptop ratios need suitable crops; do not stretch a landscape design to fit them. An unplugged display has not been configured or visually checked.

Wallpaper updates are asynchronous. A successful setter call alone is insufficient; the adapter waits for the reported image path to match. Preserve the original image bytes and settings before the first mutation. If the original mode was Spotlight, static-image restore and automatic Spotlight rotation are separate capabilities; report any unverified reactivation.

Inspect, Plan and a successful previous live application are distinct validation evidence. A portable copy of the adapter is not evidence that every target machine has been tested.
