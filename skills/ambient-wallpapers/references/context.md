# Weather and agent handoffs

## Weather

Ask for a city and, when ambiguous, a country. Device/IP location discovery is a separate opt-in, not a default. The bundled `weather_signal.py` uses Open-Meteo city geocoding and current WMO weather codes, with a fixed public HTTPS provider and no API key. It uses the city's centroid, not the person's position.

`python scripts/weather_signal.py --help` describes the fetch CLI. `signals_job.py --profile <private-profile>` refreshes opted-in weather at the configured interval, publishes a short-lived category and runs local cached selection. It preserves the previous cache on a network error. Expired signals drop out and the approved fallback remains available. Source and refresh status are recorded in the job receipt.

Categories: `clear`, `cloudy`, `rain`, `snow`, `fog`, `storm`. They can influence a new generation brief or select a suitably tagged authorized pack. They do not create visual variants by themselves. Open-Meteo data attribution should accompany shared weather-derived demonstrations: [Open-Meteo](https://open-meteo.com/).

## Dot and other agents

Use a local data-only inbox instead of an unrestricted command endpoint. An agent with authorized access to the same local workspace can publish a preferred pack and/or a short future-generation brief:

```text
python scripts/context_signals.py publish --inbox <private-inbox.json> --kind agent --source dot --ttl-minutes 60 --preferred-pack <approved-pack-id> --brief "A little more warm light and sculptural detail"
```

This is a local interoperability contract. It does not connect Dot automatically, send a message, grant folder access or authenticate a remote agent. Configure the user's allowed publishers in `context_sources`; the source label is not cryptographic authentication. An agent without local access needs an explicitly configured transport before this interface can be used.

Publishers update only their `(kind, source)` entry using a bounded lock and atomic file replacement. Expired, future-dated and non-allowlisted entries do not guide selection. Agent pack suggestions must name an authorized cached pack. The manual override wins first; then an eligible agent pick; then time/display/weather matching and fallback. Cooldown still protects agent-driven changes.

The `brief` is creative reference material for the next generation, not instructions granting new permissions. It cannot change application policy, source allowlists, provider/spend limits, the schedule or execution rules. The cached selector never executes its text. Camera, microphone, calendar and application-activity signals remain separate future adapters requiring a source and an explicit user choice.
