# Local runtime profile

The runtime handles approved cached images, not image generation or memory searches. Keep this JSON in the user's private persistent state directory. Resolve relative `asset_root` against the profile directory; every image must resolve inside that root.

`examples/profile.json` contains a disabled, generic research-station example with bundled preview images. Its previews are smaller than 4K. The signal runner does not resize them; prepare display-sized files separately before applying a production collection.

```json
{
  "version": 1,
  "enabled": false,
  "allow_apply": false,
  "asset_root": "packs",
  "fallback_pack": "station",
  "catalog": [
    {
      "id": "station",
      "approved": true,
      "tags": ["day", "night", "mobile", "docked"],
      "laptop": "station/laptop.png",
      "monitors": ["station/left.png", "station/right.png"]
    }
  ],
  "signals": {
    "allowed": ["time_of_day", "display_count"],
    "day_start": 7,
    "night_start": 19,
    "min_interval_minutes": 30
  },
  "display_roles": {},
  "manual_override": null
}
```

On macOS the bundled `macos_wallpaper.swift` uses native AppKit for static-image application with a preflight plan token; see [macos.md](macos.md). Windows and Mac restore receipts are separate and platform-specific. macOS recurring scheduling is not yet bundled.

`enabled` controls selection; `allow_apply` separately authorizes the local apply runner. Do not enable either as a side effect of creating a profile. A missing image, malformed profile, unapproved pack or unsafe path must not produce a wallpaper mutation.

Only packs matching enabled signal categories should be selected; an approved fallback covers a missing combination. A single approved pack can carry all tags, but it will not create a visible day/night difference. Different visual variants require their own approval and files.

An optional `manual_override` contains `pack_id` and an ISO8601 `until` timestamp with timezone. Use it for a temporary manually selected pack. Keep runtime state in a separate local JSON file; update it only after verified application, never after a Plan or failed apply.

`display_roles` maps local Windows device paths to `laptop` or `monitor`. Explicit roles override the adapter's aspect-ratio heuristic. Populate the private mapping from Inspect/Plan during setup, especially for a 16:9 laptop or a 3:2 external monitor. The runner checks the actual device/path plan before applying and records display identities so a same-count topology change is still noticed.

Optional context fields: `signal_inbox` is a private JSON path resolved against the profile, and `context_sources` is a per-kind source allowlist, such as `{"weather":["daily-weather"],"agent":["dot","codex"]}`. Add `weather` and/or `agent` to `signals.allowed` only when selected. See [context.md](context.md).

The `weather` block contains `enabled`, a user-supplied `city`, optional `country_code`, and `refresh_minutes` (15 to 1440, normally 60). `signals_job.py` refreshes this cache and invokes the selector. A single pack can serve every context, but a visible context change needs distinct authorized variants.

Give every newly generated collection a new pack ID and preserve its image files. This makes freshness and rollback explicit rather than silently replacing the contents of an already selected pack.

Place the preferred matching pack first in the catalog. `approved` means authorized for application: record `approval_basis` as `user_visual_choice` or `recurring_generation_policy`. A policy-authorized scheduled image has not yet been visually endorsed by the user. Preserve that distinction in feedback records.

Run `python scripts/ambient.py --help` for the exact CLI. Export a sanitized example when sharing the skill; personal evidence, actual display device IDs and absolute user paths belong only in the private copy.
