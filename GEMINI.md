# Gemini / Antigravity Instructions — friday-tony-stark-demo

Persistent memory for this project:
`/Users/dhruvsmac/Desktop/SecBrain/projects/friday-tony-stark-demo/`

## Vault First, Vault Ask

Inherit the user's global SecBrain rules.

Start meaningful tasks by reading:

1. `projects/friday-tony-stark-demo/index.md`
2. `overview.md`, latest `log.md`, `status/recent-changes.md`
3. Relevant entity/concept/source notes

Verify everything against the actual repo. Sources are immutable; the wiki is compiled working knowledge.

## Vault Writes

- Never auto-save chat/work to the vault.
- Ask first: "Do you want me to save this thread/work into Obsidian?"
- Only write if the user explicitly approves or asked this turn.
- When approved: update source/output → entities/concepts → backlinks → `index.md` → `log.md` → `status/recent-changes.md`. Maintain `[[wikilinks]]`, aliases, and `See Also`.
- Never store secrets, tokens, `.env` contents, or raw user data.

## Project Quick Facts

- Two processes (`uv run friday`, `uv run friday_voice`) over MCP/SSE on port 8000.
- WSL host-IP code is present but commented out.
- Default stack: Sarvam STT, Gemini 2.5 Flash, OpenAI TTS `nova`.
- `search_web` is a stub; README mentions a Supabase ticketing tool that isn't implemented.
