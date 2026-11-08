# Preference calibration

Use a small evidence ledger rather than a personality label:

On Windows, an optional private profile index lives at `%LOCALAPPDATA%/AmbientWallpapers/profiles.json`. Read it when present to find an existing user's local profile and preference ledger across workspaces. On other systems, use an explicitly supplied profile or a user-approved configuration directory. Keep this index outside the installed/shareable skill. Do not search unrelated files to infer taste.

| Status | Meaning | Example |
| --- | --- | --- |
| Confirmed | The user chose it or liked a visible result | Dark architecture with restrained amber lighting |
| Inferred | A hypothesis from relevant history | Interest in physical machines might translate into sculptural mechanical forms |
| Rejected | Feedback about a shown result | Blue misty landscapes were technically correct but missed the intended feel |

Store the source and a brief date/context. Do not convert an inference into a confirmed preference merely because an image was generated or applied. A visible image followed by positive feedback is stronger evidence than occupational keywords.

An effective opening is: “My read is dark, spacious architecture with a small amount of warm light. Would you prefer that to feel more industrial, more cosmic, or more abstract?” Use the user's own words when available. If the direction is unsettled, preview materially different concepts before creating a whole collection.

Keep visual taste separate from operational preferences: display sizes, upscaling permission, application permission, budget/provider choice, schedule and signal sources. A preference to keep backgrounds fresh is not a cadence or an authorization to inspect unrelated personal data.

For subsequent runs, reuse the approved art direction. Ask again only when feedback changes it or an important input is genuinely missing. Current instructions take precedence over saved notes.

Keep a local record such as:

```json
{
  "confirmed": [{"value": "dark architectural science fiction", "source": "user approved preview"}],
  "inferred": [{"value": "mechanical detail may appeal", "source": "relevant prior conversation"}],
  "rejected": [{"value": "blue misty landscapes", "source": "feedback on first set"}]
}
```

This is a generic example, not a bundled user's profile. Do not place raw chat transcripts, memory extracts, account identifiers or private local paths into an image prompt or public showcase. Distill the agreed visual requirements into the prompt. A local profile does not authorize editing global memory.
