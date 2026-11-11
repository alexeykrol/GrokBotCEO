# Shared blocks

Text blocks that several bots carry word for word. A line `[[block:<name>]]` in a bot's
`prompt.md` (or `block.md`) is replaced by `<name>.md` when the text is built
(`scripts/bot-payload-compiler.py`). One level only: a block cannot include another block.

- `routing.md` — the standard routing block: a request to change something for good goes straight
  to Bot Maker (`SendToAgent`), which clarifies it in the #Improvements channel and waits for the
  user's own yes; the bot then tells the user to go to #Improvements, read and confirm. It is in
  the main-bot block and in Mentor, and Bot Maker adds it to every bot it creates
  (`bot-payload-compiler.py compose`). The channel id is read from `config.json` at run time
  (`IMPROVEMENTS_CHANNEL_ID`), never baked in: the channel is created after the bots. Only the
  user, the main bot and Bot Maker are members (at most 6 bots per channel).
