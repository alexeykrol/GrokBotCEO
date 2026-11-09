# Getting Started with GrokBotCEO

**Version:** see [VERSION](VERSION) · **You need:** a Grok Bot account · **Time:** about 20 minutes

GrokBotCEO is a ready set of Grok Bot bots, processes and skills for running a business and a product.
You install it once by pasting one command into your Grok Bot chat. After that the bots are yours:
change them as you like.

Русская версия: [ONBOARDING.ru.md](ONBOARDING.ru.md).

---

## 1. Paste this into your Grok Bot chat

```
Install GrokBotCEO for me.

Repository: https://github.com/alexeykrol/GrokBotCEO (latest release)
Follow LOADING-INSTRUCTIONS.md from that release step by step. Do not improvise steps that are not there.

Rules:
- Ask before creating any bot. Show me the plan first and wait for my "yes".
- Never ask for passwords, tokens or keys in chat.
- Do not turn on any schedule or send any message on my behalf. Routines I set up myself.
- If a required capability is missing, stop and tell me exactly what is missing.
```

## 2. Answer a few questions

The bot asks only what the bots need to work: your timezone, the language of reports, the name of
the channel where bots post proposals, and, if you want the readers, your X and Telegram details.
Your answers are saved to `config.json` in your workspace. That file stays with you: it is never
sent anywhere and updates never touch it.

## 3. Approve the plan

The bot shows which bots it will create. Three are the core and installed by default:

| Bot | What it does |
|---|---|
| Main Grok | your main assistant and router |
| Bot Maker | creates and changes bots for you |
| Monitor | weekly report on how bots are used, and proposals to improve them |

The rest are optional: X and Telegram readers, Implementer, Translator, Week planner, Reminder,
Projects Manager, Task Manager and Repository Analyst (the last two need a connection to your
computer). Cross out what you don't need, then type `yes`.

## 4. The bot creates the bots

For each bot it prints one line: `created`, `created · NOT VERIFIED`, or `failed`.
`NOT VERIFIED` means Grok Bot did not return the full text after creation, so the bot could not
compare it with what was sent. The bot is still created; open it and look at its description if you
want to be sure.

## 5. Set up schedules yourself

The installer cannot create schedules (routines): there is no supported tool for that. The bot gives you
step-by-step instructions for each routine from `bots/<bot>/routines.md`: where to click, what to
paste. Turn them on one at a time.

---

## What you get on disk

```
<workspace>/
  grokbotceo/    the release you downloaded — do not edit, an update replaces it
  config.json    your answers
  build/         texts compiled from the release and your config (regenerated any time)
  installed/     what was actually installed: VERSION, agents.json, one .md per bot
```

`installed/` is how a future update will know whether you changed a bot by hand (see below).

## Updates

Updates are announced in the repository releases and in the author's Telegram channel. Nothing
updates by itself. When you say "update", your bot shows what changed, bot by bot, and asks first.

Updates change only algorithms and rules, never your settings in `config.json`. If you edited a
bot by hand, an update would overwrite that edit. Before that happens the bot tells you which bots
you changed and offers three options: take the update (your edit is lost), skip it, or ask Bot
Maker to merge your edit into the new version.

## Security

- Secrets never go in chat. Services (X, Telegram, Notion) are connected in the Grok Bot settings.
- No bot is created, no message sent and no schedule turned on without your "yes".
- `config.json` and everything in your workspace stay on your Grok Bot computer.

## Help

- [teaching/](teaching/) — how the bots, processes and protocols work, and how to customize them
- `bots/<bot>/prompt.md` — what each bot does and what it never does
- `company-structure/processes/` — the workflows the bots follow
