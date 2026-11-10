# Local copy — the repo on the user's own computer

**Reader:** the installer ([LOADING-INSTRUCTIONS.md](LOADING-INSTRUCTIONS.md), step 13) and Bot Maker.
This is a procedure for the bot, not a page for the user.

The user can have a **read-only copy** of their repo on their own computer. The repo itself stays
on the bot computer; the copy is replaced with a fresh one after every change. Mac and Linux only
in this release. On Windows say: "A copy on your computer is not supported on Windows yet."

## When it runs

- right after install, if the user said yes;
- after every Bot Maker commit, when `<WORKSPACE_PATH>/local-copy.json` exists;
- when the user says "refresh my copy".

## The setting

`<WORKSPACE_PATH>/local-copy.json` is `{"path": "<absolute path on the user's computer>"}`. It is
committed. No file means no copy. To create it (the user said yes, or asked "make a copy on my
computer"):

1. Tell the user about the permission question (next section).
2. On the user's computer run `uname -s && echo "$HOME"`. `Darwin` is a Mac, `Linux` is Linux.
   Anything else, or no answer: not supported yet; stop here.
3. Suggest `<home>/GrokBotCEO`, where `<home>` is the folder printed. Let the user change it.
   The path must start with `/` and must not contain quotes, `$`, backticks, backslashes or line
   breaks. It must be a new folder or an earlier copy, never a folder with the user's files.
4. Write `local-copy.json`, then `git add local-copy.json` and commit; the message records the
   user's exact yes words, `(yes: "<exact words>")`, and ends with the line `Bot: <your bot name>`.
5. Make the first copy (below).

## Permission on the user's computer

The first time a bot runs a command on the user's computer, Grok Bot asks: "Allow Grok Bot and all
Bots to run commands on your local computer?" Tell the user before it happens: expect this
question; "Allow once" is enough each time, or "Always allow" so it is not asked again. If the
user does not allow it, the copy is not made: say so in one line and go on.

## Make or refresh the copy: three steps

1. **Pack, on the bot computer:**

   ```bash
   cd <WORKSPACE_PATH>
   python3 grokbotceo/scripts/bot-mirror.py pack --workspace . --out build/local-copy.tar.gz
   ```

   It prints the archive path and the commit. It refuses if the repo has uncommitted changes:
   commit first, the copy must equal a commit. The archive holds only committed files and the
   git history; never `grokbotceo/`, `build/` or untracked files.

2. **Copy the file:** copy `<WORKSPACE_PATH>/build/local-copy.tar.gz` from the bot computer to
   `<path>.tar.gz` on the user's computer (CopyFromBox). `<path>` is the value from
   `local-copy.json`.

3. **Unpack, on the user's computer:** run the block below there, with `<path>` replaced by the
   value from `local-copy.json` in both lines at the top. It needs only `sh`, `tar`, `rm`, `mv`
   and `mkdir`; no git or python on the user's computer. It works in sh, bash and zsh.

```sh
P="<path>"
A="<path>.tar.gz"
(
M=".grokbotceo-copy"
while [ "$P" != "/" ] && [ "${P%/}" != "$P" ]; do P="${P%/}"; done
case "$P" in
  /*) ;;
  *) echo "STOP: the copy path must be absolute, got '$P'. Nothing was changed."; exit 1 ;;
esac
case "$P" in
  /|*/./*|*/../*|*/.|*/..) echo "STOP: '$P' cannot be the copy folder. Nothing was changed."; exit 1 ;;
esac
if [ -L "$P" ] || { [ -e "$P" ] && { [ ! -d "$P" ] || [ ! -f "$P/$M" ]; }; }; then
  echo "STOP: $P already exists and is not a GrokBotCEO copy. Nothing was changed."; exit 1
fi
if [ ! -f "$A" ]; then
  echo "STOP: the archive $A is not on this computer. Nothing was changed."; exit 1
fi
N="$P.new"
if [ -L "$N" ] || [ -e "$N" ]; then
  if [ ! -L "$N" ] && [ -d "$N" ] && { [ -f "$N/$M" ] || [ -z "$(ls -A "$N")" ]; }; then
    rm -rf "$N"
  else
    echo "STOP: $N exists and is not a GrokBotCEO copy. Nothing was changed."; exit 1
  fi
fi
mkdir -p "$N" || { echo "STOP: cannot create $N. Nothing was changed."; exit 1; }
if ! tar -xzf "$A" -C "$N" || [ ! -f "$N/$M" ]; then
  rm -rf "$N"
  echo "STOP: the archive could not be unpacked. The old copy is unchanged."; exit 1
fi
if [ -d "$P" ]; then
  rm -rf "$P" || { echo "STOP: cannot remove the old copy $P. The new copy is in $N."; exit 1; }
fi
mv "$N" "$P" || { echo "STOP: cannot move $N to $P."; exit 1; }
rm -f "$A"
echo "COPY UPDATED: $P"
)
```

What the block does: it refuses a path that is not absolute, and any existing folder that has no
`.grokbotceo-copy` marker file (so it never deletes a folder it did not make, such as the home
folder). It unpacks into `<path>.new`, then replaces the old copy with it and deletes the archive.

## What to tell the user

After the first copy, in two or three short sentences: where the copy is; it is read-only and is
refreshed after every change; anything edited in it is overwritten on the next refresh; to see the
history, open the folder with any git tool (or run `git log` there). After later refreshes, one
line: "The copy on your computer is updated."

## Errors

A line starting with `STOP:`, a failed file copy, or a refused permission: tell the user in one
plain line what happened. Do not retry in a loop. The repo on the bot computer is not affected.
If the folder already exists and is not a copy, the user may pick another path: change
`local-copy.json`, commit, and try once. The user can ask "refresh my copy" at any time.

## Turning it off

The user tells Bot Maker to stop the copy. Bot Maker runs `git rm local-copy.json` and commits.
Nothing is refreshed after that. The folder on the user's computer stays; the user may delete it.
