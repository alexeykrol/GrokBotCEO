# Getting Started with BotCEO

**Version:** see [VERSION](VERSION) · **You need:** a Grok Bot account · **Time:** 20–30 minutes

BotCEO is a ready set of bots for Grok Bot, for running a business and a product. Your own main bot
learns the system; five new bots arrive: Bot Maker, Mentor, Reminder, Translator and Monitor; the
#Improvements channel is where changes are agreed; a repo mirrors your system. Mentor then takes you
through a short course, in small steps, that ends with your first own bot. You install it by
pasting one command into your Grok Bot chat. After that the bots are yours.

Русская версия: [ONBOARDING.ru.md](ONBOARDING.ru.md).

---

## 1. Paste this into your Grok Bot chat

```
Install BotCEO for me.

Repository: https://github.com/alexeykrol/GrokBotCEO (latest release)
Follow LOADING-INSTRUCTIONS.md from that release step by step. Do not improvise steps that are not there.

Rules:
- Ask before creating any bot. Show me the plan first and wait for my "yes".
- Never ask for passwords, tokens or keys in chat.
- Do not turn on any schedule unless I choose it in the plan. Do not send any message on my behalf.
- If a required capability is missing, stop and tell me exactly what is missing.
```

## 2. Check one setting

The bot fills in `config.json` itself: the path of your workspace and the names of the bots
(in your language, except Bot Maker). It asks you only two things during the whole install, each
with answer buttons: your answer to the plan (with or without routines, or no), and whether you
want a copy on your own computer. The file stays on
your Grok Bot computer (and in the optional copy on your own computer): it is never sent anywhere
else and updates never touch it.

## 3. Approve the plan

It shows the plan:

| What | What it does |
|---|---|
| your main bot | not a new bot: it learns BotCEO and keeps its name |
| Bot Maker (new) | creates and changes bots for you |
| Mentor (new) | a short course on how Grok Bot and your system work; answers how things work |
| Reminder (new) | keeps your one-off tasks and reminds you on time |
| Translator (new) | translates a text or a post in two passes; never publishes anything |
| Monitor (new) | a weekly report on how your bots work, with proposals; changes nothing |
| two routines (only "with routines") | Reminder: today's tasks every morning at 09:00; Monitor: the weekly report every Sunday at 20:00 (your time) |
| #Improvements channel (new; named in your language) | you, your main bot and Bot Maker; Bot Maker agrees every change with you here |

Plus a git repo in your workspace that mirrors your system. Tap **Yes, with routines** or **Yes,
without routines**. You can turn the routines on or off later in each bot's chat.

## 4. The bot does it

For each bot it prints one line: `created · VERIFIED`, `created · MISMATCH` or
`created · NOT VERIFIED` (for your main bot: `extended · ...`). After creating a bot, the installer reads the bot's file on the bot
computer and compares its text with what was sent. `VERIFIED` means they are equal, `MISMATCH`
means they differ. `NOT VERIFIED` means the file could not be read, so nothing could be compared;
the bot is still created. If you chose routines, it asks Reminder and Monitor to set up their own
routine (each bot does it itself; if the bot does not know your timezone, it asks you for your
city in its chat). Then it creates the #Improvements channel, saves everything to the repo
(including your main bot's old text, so it can be rolled back) and makes the first commit. If
something does not work (for example, the channel or the change to your main bot), it says so in
one line and goes on; Bot Maker can do it later.

Then it offers a read-only copy of the repo on your own computer (Mac or Linux), refreshed after
every change: tap Yes or No. If yes, Grok Bot asks "Allow Grok Bot and all Bots to run commands on
your local computer?"; "Allow once" is enough.

## 5. Open Mentor, take the course and make your first bot

At the end the bot tells you to open Mentor in the list on the left. Write to Mentor:

```
Let's start the course
```

The course is in Russian for now (for a Russian speaker: «Начнём курс»). Mentor goes one small step
at a time:

1. what is installed and where;
2. four ideas: bot, channel, routine, connection;
3. the golden rule: to change something for good, tell any bot, right in its chat; it passes the
   request to Bot Maker, which agrees it with you in #Improvements and changes nothing before your
   "yes";
4. your first own bot: Mentor gives you one sentence to paste right there; then you open the
   channel #Improvements, read what Bot Maker wrote and confirm;
5. what only you can do, one short exercise each: create a channel (its name starts with `#`),
   invite bots (at most 6 in a channel), rename and delete a channel, and make a section «Your bots»
   in the list on the left. Bots cannot rename or delete a channel or make a section;
6. how to look at your system, and what comes next.

You can stop the course any time and come back later: say "Let's continue the course". Any time,
ask Mentor how something works: it answers from its knowledge base and says honestly when
something is not verified yet.

---

## What you get on disk

```
<workspace>/          a git repo, no remote
  grokbotceo/         the release you downloaded — do not edit, an update replaces it
  config.json         your values
  local-copy.json     optional: where the copy on your own computer is
  VERSION             the installed version
  bots/core/          your main bot (its text now and before) and the five installed bots: text and a small record each
  bots/my/            bots you make through Bot Maker
  bots/marketplace/   copies (name and text only) of bots you import from the marketplace
  channels/           one file per channel: id, members, purpose
  mentor/             your place in the course and Mentor's knowledge base
  data/               Reminder's tasks and Monitor's weekly numbers
  build/              texts compiled from the release and your config (regenerated any time)
```

Every change Bot Maker makes is a commit; each commit says which bot made it and quotes your "yes". Imported a bot
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
- Translator never publishes; Monitor never changes a bot; Reminder never writes to anyone but you.
- `config.json` and your repo live on your Grok Bot computer. Nothing is pushed anywhere. The
  optional copy goes only to your own computer, and only after your yes.

## Help

- Ask Mentor: "Let's start the course", or any question about how it works
- Ask your main bot: "what do I have installed"
- `bots/<bot>/prompt.md` — what each bot does and what it never does
