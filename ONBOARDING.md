# Getting Started with GrokBotCEO

**Version:** see [VERSION](VERSION) · **You need:** a Grok Bot account · **Time:** 20–30 minutes

GrokBotCEO is a ready set of Grok Bot bots for running a business and a product. This release is
the core: two bots, a repo that mirrors your system, and a short tour that ends with your first own
bot. You install it by pasting one command into your Grok Bot chat. After that the bots are yours.

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

## 2. Check one setting

The bot fills in `config.json` itself: the path of your workspace and the name of Bot Maker. It
shows you the file; correct the path only if it is wrong. Nothing else is asked. The file stays on
your Grok Bot computer (and in the optional copy on your own computer): it is never sent anywhere
else and updates never touch it.

## 3. Approve the plan

The bot shows what it will create:

| Bot | What it does |
|---|---|
| Main Grok | your main assistant; gives the tour and answers how things work |
| Bot Maker | creates and changes bots for you |

Plus a git repo in your workspace that mirrors your system. Type `yes`.

## 4. The bot creates the bots

For each bot it prints one line: `created · VERIFIED`, `created · MISMATCH` or
`created · NOT VERIFIED`. After creating a bot, the installer reads the bot's file on the bot
computer and compares its text with what was sent. `VERIFIED` means they are equal, `MISMATCH`
means they differ. `NOT VERIFIED` means the file could not be read, so nothing could be compared;
the bot is still created. Then it saves both bots to the repo and makes the first commit.

Then it offers a read-only copy of the repo on your own computer (Mac or Linux), refreshed after
every change: say yes or no. If yes, Grok Bot asks "Allow Grok Bot and all Bots to run commands on
your local computer?"; "Allow once" is enough.

## 5. Take the tour and make your first bot

The tour starts right away, a step or two at a time:

1. what is installed and where;
2. four ideas: bot, channel, routine, connection;
3. the golden rule: to change a bot for good, tell Bot Maker, not the bot itself;
4. your first own bot: pick a simple job, tell Bot Maker, say `yes`;
5. how to look at your system, and what comes next.

There are no routines to set up in this release. You can restart the tour any time: say "tour" to
Main Grok.

---

## What you get on disk

```
<workspace>/          a git repo, no remote
  grokbotceo/         the release you downloaded — do not edit, an update replaces it
  config.json         your values
  local-copy.json     optional: where the copy on your own computer is
  VERSION             the installed version
  bots/core/          Main Grok and Bot Maker as installed: text and a small record each
  bots/my/            bots you make through Bot Maker
  bots/marketplace/   copies (name and text only) of bots you import from the marketplace
  build/              texts compiled from the release and your config (regenerated any time)
```

Every change Bot Maker makes is a commit, and each commit says which bot made it. Imported a bot
from the marketplace? Tell Bot Maker "I installed a bot": there is no automatic signal for that.
A copy on GitHub is optional and comes later.

## Updates

Updates are announced in the repository releases and in the author's Telegram channel. Nothing
updates by itself; the update procedure comes with the next stage. Its rules: your bot shows what
changed, bot by bot, and asks first. `config.json`, `bots/my/` and `bots/marketplace/` are never
touched. If you changed a core bot, the update asks before touching it: take the update, skip it,
or ask Bot Maker to carry your change into the new version.

## Security

- Secrets never go in chat. Services are connected in the Grok Bot settings.
- No bot is created or changed, no message sent and no routine turned on without your "yes".
- `config.json` and your repo live on your Grok Bot computer. Nothing is pushed anywhere. The
  optional copy goes only to your own computer, and only after your yes.

## Help

- Ask Main Grok: "tour", "what do I have installed", or any question about how it works
- `bots/<bot>/prompt.md` — what each bot does and what it never does
