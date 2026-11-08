# Recurring generation and local signals

## Two separate jobs

| Job | Purpose | Typical cadence |
| --- | --- | --- |
| Fresh generation | Make a new coordinated set within the approved art direction | Weekly, or daily if explicitly chosen |
| Cached selection | Select a previously approved pack for the current context | Time boundary or display change |

Do not regenerate on every signal poll. Reuse approved images, respect a manual override, and keep the last valid set when an asset, tool or signal is unavailable.

## Scheduled generation

Capture the selected cadence, local timezone, image provider/cost boundary, maximum set size, and whether the user authorizes recurring application or wants previews. A speculative “maybe weekly” is a design request; it is not an active schedule.

When Codex's automation tool is available, prefer its existing-thread heartbeat for a continuation of this task. Inspect existing automations before creating another. Use a user-readable prompt referencing the installed skill and the private local preference/profile files; do not copy private history into the scheduler prompt. Use the scheduling tool rather than hand-writing automation directives.

Each run should read the approved direction, inspect displays, make at most the authorized number of images, verify files, and apply only if recurring application is authorized. If image generation or OS permission is unavailable, leave the current wallpaper in place and report that the refresh did not complete. Never silently switch to a paid API. Log generated, prepared, applied and visually approved as different states.

Local generation/application depends on the computer, app, tools and permissions being available. A created schedule proves configuration, not a successful future refresh. A cloud task that cannot reach the desktop cannot update its wallpaper.

Current official guidance: [Scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app). Recheck the available scheduling tool before activation; host capabilities can change.

## Local signal selection

The bundled `ambient.py` runner plans or applies approved cached packs. Inputs include local time, connected displays and validated cached context. Its state prevents repeated application and enforces a cooldown. A manual choice with an expiry takes priority and bypasses automatic-change cooldown.

For an unattended local runner, use `powershell -NoProfile -File scripts/install_signal_task.ps1 -Mode Plan` with the private profile and an explicit `pythonw.exe` path; consult `-?` for exact parameters. Inspect its planned action before choosing Install. It polls every15 minutes and runs at user logon, through an interactive limited account, with no stored password or wake-from-sleep setting. `signals_job.py` refreshes weather no more frequently than configured (normally hourly), then chooses cached art. Test a one-shot plan and authorized apply first. Task registration proves configuration, not every future display-change flow. Inspect and Remove are available for the exact task name.

## Further signals

Weather and Dot/agent handoffs are implemented as optional adapters; see [context.md](context.md). Calendar, application activity, mood, microphone and camera are separate ideas requiring their own source, purpose and explicit choice. Do not infer sensitive personal state from those sources.

New signal adapters should output a small category such as `rain` or `focus`, not raw private content. Selection should remain stable when signals conflict: manual override, then the user's explicit priority order, then a known approved fallback. Keep the initial implementation narrow rather than claiming unsupported integrations.
