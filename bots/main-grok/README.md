# Main bot block

**Stage 1 core.** Not a bot of its own. The installer does not create a new main bot: it adds
this block to the user's own main bot (the default Grok Bot they already have) with
`UpdateAgent`. The bot keeps its name.

## How it is added

- `scripts/bot-payload-compiler.py extend --bot main-grok --agent-id <id>` reads the bot's
  current text from its `profile.json` on the bot computer and writes:
  - `build/main-grok.previous.md` — the text as it was (kept for rollback);
  - `build/main-grok.md` — the new full text: the old text (trailing whitespace trimmed), a blank
    line, then this block;
  - `build/main-grok.payload.json` — the `UpdateAgent` payload (`agent_id`, `description`; no name).
- The write check compares the bot's `profile.json` with `build/main-grok.md`.
- In the user's repo: `bots/core/main-grok/previous.md` (the old text), `prompt.md` (the exact text
  the bot runs on), `agent.json`.
- Whether a bot can `UpdateAgent` itself is not verified. If it fails, the installer says so in
  one line and goes on; the user can later ask Bot Maker "add GrokBotCEO to my main bot", which
  runs the same `extend` and applies it after the user's yes.

## What the block says

- The main bot is the everyday assistant and does that work itself; it never owns a routine.
- Before passing a new task or process on, it works out with the user: the job, which bot owns
  it, what starts it (trigger or schedule), input and output.
- "How does this work", "tour", "what can I do" → Mentor. "Refresh my copy" → Bot Maker.
- The standard routing block (`bots/_blocks/routing.md`): lasting changes go to the Improvements
  channel.

## Anti-jobs

- Does not create, change or delete bots, and does not write to the repo.
- Does not turn on routines or ask for secrets in chat.

## Files

- `block.md` — the block; placeholders `{{WORKSPACE_PATH}}`, `{{BOT_MAKER_BOT}}`, `{{MENTOR_BOT}}`;
  includes `[[block:routing]]`
