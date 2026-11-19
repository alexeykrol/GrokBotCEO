# Which License Covers Which File

Version 1 · 19 November 2026 · applies to release 0.3.0

Copyright © 2026 Alexey Krol.

This package contains two kinds of material under two different licenses: an **open part** that you may
use, change and pass on with credit to us, and **course materials** that stay all rights reserved. Paths are relative to the
package root.

| Path | What it is | Governed by |
|---|---|---|
| `bots/**` | bot instructions and settings | Open part: `LICENSE` (BotCEO License 1.0) + `NOTICE` |
| `company-structure/**` | functions, processes and protocols you adapt to your company | Open part |
| `scripts/**` | tools and tests | Open part |
| `course/progress.py`, `course/kb-box/**` | course engine code | Open part |
| `course/MENTOR-RUNTIME.md`, `course/SCHEMA.md`, `course/EVENT-SCHEMA.md` | engine instructions and format descriptions | Open part |
| `config.example.json`, `config.schema.md`, `VERSION`, `MANIFEST.sha256` | configuration and package data | Open part |
| `README*.md`, `ONBOARDING*.md`, `LOADING-INSTRUCTIONS.md`, `UPDATE.md`, `LOCAL-COPY.md` | installation and usage documentation | Open part |
| `course/lessons/**`, `course/sections/**` | lessons | Course Materials: `COURSE-LICENSE.md` |
| `course/kb/**`, `course/kb-markup/**` | knowledge base and its markup | Course Materials |
| `course/COMPETENCIES.md`, `course/course.json`, `course/scenario-registry.tsv` | course plan, competencies, quiz scenarios | Course Materials |
| `teaching/**` | teaching guides | Course Materials |
| `LICENSE`, `NOTICE`, `COURSE-LICENSE.md`, `TRADEMARKS.md`, `LICENSE-MAP.md`, `TERMS.md`, `TERMS-NOTICE*.md`, `PRIVACY.md` | the legal texts themselves | may be copied unchanged |

Third-party material, if a release contains any, is named in the README ("Credits") with its source
and terms, and stays under those terms.

Rules for anything not listed:

1. A file under `course/` that is not listed above is Course Materials.
2. Any other file that is not listed is in the open part.
3. Files that you create yourself in your workspace (your settings, your progress, your own bots'
   data) are yours. Changed versions of our files remain subject to the license of the original file.

Names and logos are covered by `TRADEMARKS.md`, not by either license. The BotCEO Terms of Use
(`TERMS.md`) apply to the whole package.
