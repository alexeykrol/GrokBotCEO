# telegram-translation-publishing — Publish Approved Translation

**Called by:** Translator bot (after owner approval)

## Purpose

Publish final approved translation to designated Telegram channel.

## Inputs

- Final translation text
- Source post link
- Target Telegram channel ID
- Owner approval evidence

## Outputs

- Translation posted to {{PUBLISHING_CHANNEL}}
- Publication record (timestamp, link, source)
- Confirmation to owner

## Success Criteria

- Translation posted successfully
- Link to published message returned
- Record saved for tracking

Related: Translator bot, two-pass translation workflow
