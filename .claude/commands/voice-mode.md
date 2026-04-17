---
description: Set FRIDAY's voice mode (pipeline | realtime_gemini | realtime_openai)
argument-hint: <mode>
---

Update `VOICE_MODE` in `.env` to `$ARGUMENTS`.

Valid values: `pipeline`, `realtime_gemini`, `realtime_openai`.

Steps:
1. Validate the argument is one of the three allowed values. If not, show the list and stop.
2. Read `.env`. If `VOICE_MODE=` exists, replace the line. Otherwise, append `VOICE_MODE=<mode>`.
3. Confirm the change back to the user and remind them to restart `uv run friday_voice` for it to take effect.

Do not touch any other env vars.
