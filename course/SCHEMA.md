# Mentor course — machine contract

This file defines the format of `course/course.json`, the lesson texts in `course/lessons/`, the
knowledge base in `course/kb/`, and the progress file Mentor keeps in the user's workspace. How
Mentor runs the course on top of these formats: `course/MENTOR-RUNTIME.md`.
Checked by `scripts/test-course.py`. A rule here that the test does not check is marked *(not tested)*.

The course structure is language-independent; user-facing strings are in `course.language`.

## 1. `course.json`

```json
{
  "course": {
    "id": "mentor",
    "version": "0.1.0",
    "language": "ru",
    "sections": [ ...section ]
  }
}
```

| Field | Type | Rule |
|---|---|---|
| `id` | string | stable course id |
| `version` | string | semver; bump on any change to step ids or order (see §4 resume) |
| `language` | string | `"ru"` for now |
| `sections` | array | exactly the course sections in order (`S1`..`S4`) |

### Section

| Field | Type | Rule |
|---|---|---|
| `id` | string | `S<n>` |
| `title` | string | user-facing |
| `goal` | string | user-facing; one sentence: what the person can do after the section |
| `lessons` | array | ≥ 1 lesson, in order |

**End checkpoint.** The last step of the last lesson of every section is a `checkpoint` step
(§2.4). There is no separate section-level field: steps stay one flat, ordered sequence.

### Lesson

| Field | Type | Rule |
|---|---|---|
| `id` | string | `S<n>.L<nn>`, e.g. `S1.L03` |
| `title` | string | user-facing |
| `competencies` | array of string | IDs from `COMPETENCIES.md`, pattern `P<n>.<nn>` (e.g. `P1.03`) |
| `text` | string | path relative to `course/`: `lessons/<file>.md`; the file must exist |
| `draft` | bool | optional; `true` = placeholder, content not written yet |
| `needs` | array of string | optional; product gaps the practical part depends on (gap numbers of `COMPETENCIES.md`). Mentor teaches the lesson and skips its exercises with "feature coming" |
| `steps` | array | ≥ 1 step, in order |

## 2. Steps

Common fields of every step:

| Field | Type | Rule |
|---|---|---|
| `id` | string | unique in the whole course; convention `<lesson id>.s<nn>`, e.g. `S1.L01.s03` |
| `type` | string | `explain` / `exercise` / `quiz` / `checkpoint` / `branch` |
| `unverified` | bool | optional; `true` = the platform fact behind the step is not checked in a live run yet: Mentor phrases it softly and, if the user reports it is not possible, records the exercise `skipped` with the reason |
| `next` | string | optional; step id. Default: the following step in course order (next step of the lesson, then first step of the next lesson, then first step of the next section) |

Course order = sections in order → lessons in order → steps in order.

### 2.1 `explain`

| Field | Type | Rule |
|---|---|---|
| `text` | string | short user-facing text, **or** |
| `text_ref` | string | anchor in the lesson file, e.g. `lessons/s1-sections.md#что-такое-раздел` |
| `example` | string | **required**, non-empty, exactly one concrete example (U9, U15) |

At least one of `text` / `text_ref`.

### 2.2 `exercise`

| Field | Type | Rule |
|---|---|---|
| `task` | string | user-facing; **one action** (U9) |
| `expected_result` | string | user-facing; what the person sees when it worked |
| `check` | object | `{ "method": <method>, "detail": <string> }` — how Mentor verifies |
| `on_success` | string | user-facing |
| `on_fail` | object | `{ "hint": <user-facing string>, "retry": <bool> }` |
| `only_human` | bool | `true` = bots have no tool for this (U14); Mentor must not do it for the person |

`check.method` — exactly one of:

| Method | Mentor does | `detail` holds |
|---|---|---|
| `workspace_file` | checks a file exists / contains something in the user's workspace | path and what to look for |
| `list_sections` | calls `ListSections`, looks for the expected section or bot placement | expected section name / placement |
| `config_key` | reads a key in the user's settings file | key and expected value |
| `user_confirm_form` | asks with a form: [Сделал] [Не получилось] (U7) | what the person confirms |
| `agent_tool` | calls a named platform tool and inspects the result | tool name + expectation |

`detail` is for Mentor only and may contain tool names and paths; it is never shown to the user (U4).

Exercise result is `passed` or `skipped`. Mentor always offers [Пропустить] next to the retry; a
skipped exercise does not block the course *(not tested)*.

### 2.3 `quiz`

| Field | Type | Rule |
|---|---|---|
| `question` | string | user-facing |
| `options` | array | **exactly 3** `{ "id", "text", "correct": bool, "reaction" }`; **exactly one** `correct: true`; every `reaction` non-empty |

Shown as a one-choice form (buttons, U7). Wrong answer → show its `reaction`, ask again; after the
3rd wrong attempt Mentor shows the correct option with its reaction and moves on *(not tested)*.
Every attempt is counted in progress (§4).

### 2.4 `checkpoint`

| Field | Type | Rule |
|---|---|---|
| `text` | string | user-facing summary of the section |
| `options` | array | exactly two, shown as a one-choice form |

```json
"options": [
  { "id": "continue", "label": "Дальше: Наша система", "target": "S2",     "text": "..." },
  { "id": "pause",    "label": "Пауза — поиграю сам",  "text": "..." }
]
```

- `continue.target` = id of the next section (its first step), or `"finish"` in the last section.
- `pause` → progress `paused_at` is set; Mentor resumes from the next section on the person's return.
- `text` of each option is what Mentor says after the press.

### 2.5 `branch` (decision tree)

No user-facing text; Mentor evaluates it silently.

```json
{
  "id": "S1.L01.s04", "type": "branch",
  "cases": [
    { "when": { "step": "S1.L01.s03", "attempts_min": 2 }, "next": "S1.L01.s05" }
  ],
  "default": "S1.L01.s06"
}
```

`when` refers to a previous step and holds exactly one condition:

| Condition | True when |
|---|---|
| `answer: <option id>` | the final quiz answer of `step` is this option |
| `attempts_min: <int>` | the quiz `step` took at least this many attempts |
| `result: "passed" \| "skipped"` | the exercise `step` ended with this result |

Cases are evaluated in order; first match wins; otherwise `default`. `step`, every `next` and
`default` must be existing step ids.

### 2.6 User-facing fields and language (U4)

User-facing: `title`, `goal`, `text` (on steps), `example`, `task`, `expected_result`, `on_success`,
`on_fail.hint`, `question`, `options[].text`, `options[].reaction`, `options[].label`.
Not user-facing: `id`, `type`, `next`, `check.*`, `lesson.text` (a path), `text_ref`, `cases`, `default`.

User-facing strings and lesson files contain no git, repo, commit, GitHub, config.json, payload, file
paths or file extensions — plain words only.

## 3. Lesson texts — `course/lessons/*.md`

One file per lesson (or shared by a few lessons of one topic). Plain human text, short paragraphs,
one example per idea. Headings are anchors for `text_ref`. Same language rule as §2.6.

## 4. Progress — `mentor/progress.json` in the user's workspace

```json
{
  "course_version": "0.1.0",
  "current": "S1.L01.s03",
  "completed": ["S1.L01.s01", "S1.L01.s02"],
  "quiz": { "S1.L01.s03": { "option": "b", "attempts": 2 } },
  "exercises": { "S1.L01.s02": "passed" },
  "skip_reasons": {},
  "paused_at": null,
  "updated": "2026-11-10T12:00:00Z"
}
```

| Field | Rule |
|---|---|
| `course_version` | version of `course.json` the progress was written against |
| `current` | step id to show next |
| `completed` | step ids done, in order |
| `quiz` | `{step_id: {option, attempts}}` — `option` = final chosen option id |
| `exercises` | `{step_id: "passed" \| "skipped"}` |
| `skip_reasons` | `{step_id: string}` — why a step was skipped: the user's words for an `unverified` step that did not work, or `feature coming` for a lesson with `needs` |
| `paused_at` | step id of a `pause` press, else `null` |
| `updated` | ISO 8601 UTC |

**Resume.** Start at `current`. If `course_version` differs from `course.json`: keep entries whose
step id still exists, drop unknown ids; if `current` no longer exists, start at the first step after
the last surviving `completed` id in course order; then write the new `course_version`.

**Saving.** Mentor writes the file after every step and saves it to history (at the end of a
lesson, at a checkpoint, when the user stops; one commit may hold several steps) with the usual commit
rules of the system: author `GrokBotCEO bots`, message ends with the line `Bot: Mentor`. Progress is
Mentor's own bookkeeping, so the `(yes: "...")` line for user-approved changes is not needed
*(not tested)*.

## 5. Knowledge base — `course/kb/*.md`

One article per file, our own short retelling for a beginner (not a copy of documentation):

```markdown
---
id: sections
title: Разделы в списке слева
sources:
  - https://docs.x.ai/grok-bot/bots
updated: 2026-11-10
---
Text...
```

- `id` unique, `title` user-facing, `sources` ≥ 1 URL, `updated` ISO date.
- Mentor answers questions outside the current step **only** from `kb/`, in plain words with an
  example; if `kb/` has no answer, it says so honestly.
