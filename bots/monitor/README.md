# Monitor

**Installed bot.** A weekly report on how the user's bots are used, which are slow or heavy, and
proposals to improve them. It reports; it never changes anything. Its own bot with its own name in
the sidebar (`{{MONITOR_BOT}}` from `config.json`: `Monitor`, or the same word in the user's
language).

## What it does

- Reads each bot's week (`ReadTranscript`) and the shared bot computer (uptime, memory, disk).
- Report: a table per bot (messages and runs, response time median / max, load, change vs last
  week), the busiest, slowest and heaviest bots, candidates to merge or delete; every number with
  its source; "Open questions" and "Guesses and gaps" at the end.
- Proposals: recurring failures, repeated requests (skill candidates), repeated instructions (rule
  candidates). It sends them to Bot Maker (`SendToAgent`), which shows each change in #Improvements
  and applies it only after the user's yes. Monitor is not a member of #Improvements.
- Keeps its numbers in `data/monitor/` in the user's workspace (`<YYYY-Www>.json`,
  `proposals.jsonl`).
- Weekly report routine (`weekly report`, Sunday 20:00 in the user's timezone): created only after
  the user's yes, in the install plan ("Yes, with routines") or in Monitor's chat later. See
  [routines.md](routines.md).
- Carries the standard routing block (`bots/_blocks/routing.md`).

## Honest limits

Per-bot CPU and memory do not exist (one shared computer; models run on the server), and token or
billing use per bot is not visible: Monitor points to Settings → Usage. Whether `ReadTranscript` is
available on every account is not verified; without it Monitor says so and reports what it can read.

## Anti-jobs

- Never changes, pauses or deletes bots, skills or routines (only its own routine, on request).
- Never quotes the user's conversations beyond counts, timings and short labels.
- Writes only to `data/monitor/`; sends only to the user and Bot Maker.
- Never asks for passwords, tokens or keys.

## Files

- `profile.json` — name only: `{{MONITOR_BOT}}`
- `prompt.md` — the bot's full text; placeholders `{{MONITOR_BOT}}`, `{{WORKSPACE_PATH}}`,
  `{{BOT_MAKER_BOT}}`; includes `[[block:routing]]`
- `routines.md` — the routine it may create, and when
