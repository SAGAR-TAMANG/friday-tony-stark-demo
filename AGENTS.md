# Codex / Agents Instructions — friday-tony-stark-demo

Persistent memory for this project lives at:
`/Users/dhruvsmac/Desktop/SecBrain/projects/friday-tony-stark-demo/`

## Vault First, Vault Ask

Inherit the user's global SecBrain rules.

Before meaningful work:

1. Read `projects/friday-tony-stark-demo/index.md`.
2. Read `overview.md`, latest `log.md` entries, `status/recent-changes.md`.
3. Read relevant entity/concept/source notes.
4. Verify wiki claims against repo code, tests, and live services. Sources in `sources/` are immutable; the wiki is the compiled working knowledge.

## Vault Writes

- Do not auto-save chat or work to the vault.
- Ask the user first: "Do you want me to save this thread/work into Obsidian?"
- Only write if explicitly approved or requested this turn.
- When approved, update: source/output → affected entities/concepts → backlinks → `index.md` → `log.md` → `status/recent-changes.md`.
- Maintain `[[wikilinks]]`, aliases, `See Also`.
- Never store API keys, LiveKit creds, `.env` contents, or raw user data.

## Project Quick Facts

- Two processes: MCP server (`uv run friday`) and LiveKit voice agent (`uv run friday_voice`).
- MCP endpoint hardcoded at `http://127.0.0.1:8000/sse`; WSL host-IP resolver is dead code.
- Default providers: Sarvam STT, Gemini 2.5 Flash LLM, OpenAI `nova` TTS.
- `friday/tools/web.py:search_web` is a stub. Several tools referenced in README/docstrings do not exist.


<claude-mem-context>
# Memory Context

# $CMEM Friday 2026-06-06 2:11am GMT+5:30

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 1 obs (315t read) | 4,753t work | 93% savings

### Jun 6, 2026
1170 12:52a 🔵 Friday voice AI backend startup behavior and expected "errors"

Access 5k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>