# telegram-translation-publishing — Publish Approved Translation

**Called by:** a publishing bot you make, after the owner's approval. The installed Translator never publishes: it gives you the final text and you publish it yourself.

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

Related: two-pass translation workflow
