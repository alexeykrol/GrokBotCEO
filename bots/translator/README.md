# Translator

**Role:** Translates content to Russian via two-pass Codex pipeline

**Key responsibility:** High-quality translation with Codex, approval workflow, publishing to Telegram

## What Translator Does

- Receives translation requests from owner (never auto-triggered by readers)
- Two-pass translation: first pass → owner review → corrections → second pass
- Posts final approved translation to designated Telegram channel
- Maintains translation quality standards
- Tracks translation history

**Two-pass Codex pipeline:** First pass produces draft, owner reviews and provides feedback, second pass incorporates corrections for final version

## Anti-Jobs

Translator does NOT:
- Accept translation requests from bots (only from owner)
- Auto-translate reader selections (owner decides what to translate)
- Publish without owner's explicit approval
- Translate without context or source link

## Files Structure

- `README.md` — This file (role and setup notes)
- `profile.json` — Bot configuration *(template in progress)*
- `prompt.md` — Translation workflow and quality standards *(template in progress)*
- No routines (translation is on-demand only)

## Setup Notes

1. Configure Telegram channel for publishing translations
2. Set translation quality standards (accuracy, tone, terminology)
3. Define approval workflow (draft → review → corrections → final)
4. Specify target language (template uses Russian)

---

**Status:** v0.1 placeholder (full template in progress)
