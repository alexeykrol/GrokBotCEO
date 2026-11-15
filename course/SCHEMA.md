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
| `version` | string | semver; bump on any change to step ids, order or content, with a `changes` entry (§2.7) |
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

The result is recorded by `progress.py` (§4): `confirmed` (checked, scored), `said_done` ([Сделал]), `shown` or `skipped`; for `branch` `result`, `passed` = `confirmed` or `said_done`. Mentor always offers [Пропустить] next to the retry; a
skipped exercise does not block the course *(not tested)*.

### 2.3 `quiz`

| Field | Type | Rule |
|---|---|---|
| `question` | string | user-facing |
| `options` | array | **exactly 3** `{ "id", "text", "correct": bool, "reaction" }`; **exactly one** `correct: true`; every `reaction` non-empty |
| `primary_scenario_id` | string | optional; id of the primary situation (the step's own `question`/`options`). Default: the step id |
| `situations` | array | optional; extra situations in show priority: `{ "id", "question", "options", "rubric_ref" }` |
| `primary_rubric_ref` | string | optional (exercise and quiz); the primary situation's rubric: a rubric id of this step or `-` (below) |

Shown as a one-choice form (buttons, U7). Wrong answer → show its `reaction`, ask again; after the
3rd wrong attempt Mentor shows the correct option with its reaction and moves on *(not tested)*.
Every attempt is counted in progress (§4).

**Situations.** A quiz is one check with one or more situations; the first is the primary (the step's
own `question`/`options`, id `primary_scenario_id`), the rest are `situations`, in show priority (the
list order is meaningful and never sorted). A content edit of the primary changes
`primary_scenario_id` (e.g. `S1.L13.s03.v2`), never the step id: route, history, X/N and the number of
required checks stay. Rules (checked by the build and `scripts/test-course.py`):
- a situation `id` is unique in the course; option ids are unique **within the step over all its
  situations** (an extra situation has its own ids, e.g. `p1`…`p3`), so an id of one situation is
  never accepted in another;
- exactly 3 options, exactly one `correct`, every `text` and `reaction` non-empty;
- `rubric_ref` is `-` or an existing rubric. A rubric is a condition of **scoring**, not of existence:
  a situation with `-` or a non-accepted rubric exists and is shown, it is just not scored;
- **display labels are positions**: the label of an option is its position in the situation's
  `options` array (a, b, c). `key`, `reaction` and the expected answer are fields of the option and
  move with it; an option id is not a letter.

**The primary situation's rubric** (design p2b §12, addendum 1, agreed with Codex 3d625e0d). Rubric
rows name a step, not a situation, so the build resolves which one is the primary's:
- `primary_rubric_ref` set: `-` is an explicit absence (no rubric, no lookup in the table); an id must be
  an existing rubric **of this step** and is used as is. The field does not accept anything: a
  non-accepted rubric named here is allowed and simply gives no scoring.
- not set: candidates = rubric rows of the step that **no extra situation of the step names**; exactly
  one candidate → it; no candidate and exactly one row of the step (shared with a situation) → it; no
  rows → `-`; anything else (two or more candidates, or no candidate with two or more named rows) fails
  the build with `ambiguous primary rubric: set primary_rubric_ref`.
- the result never depends on the order of the rubric rows, and adding situations never silently
  rebinds the primary or downgrades it to `-`/not eligible: where it would be ambiguous the build stops.
- the field is how the rubric is referenced, not content: it is not hashed into `content_version` or
  `answer_version` (the resolved rubric's text is, §2.7, §2.8). Writing the choice the build would infer
  keeps both versions; changing the rubric's text changes the answer.

Every reader takes a situation through one resolver, `Course.situation(step, scenario_id)` in
`progress.py` → `{question, options, key, rubric_ref}`.

**Balance** (`scripts/quiz-balance.py`, algorithm `p2b-balance-1`): over every shown situation the
correct option's position should stay within [0.25; 0.42] per letter, without runs of 3, and the
correct option should not be the strictly longest in more than half of them (a tie for the longest
does not count). These are warnings of `test-course.py`, not build failures.

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

### 2.7 Generated fields (written by `scripts/course-merge.py`, never by hand)

Every step: `content_version` (sha256, 16 hex, of the step's content, its `text_ref` section, the
claims it depends on and, for checks, rubric and scenarios), `basis` (`claims` / `normative` /
`unmapped`), `claims`, `claims_status` (`verified` / `unverified` / `disputed` / `-`).
Exercise and quiz: `route` (`main` / `branch` / `optional_practice`), `required`, `eligible`
(claims all verified, or normative with an accepted rubric), `rubric_ref` (the primary situation's
rubric, resolved as in §2.3), `scenarios` (`[{id, option_ids, rubric_ref}]`, one per situation in show priority,
`option_ids` sorted by id). Course level: `rubrics` `{id: {step, status, text}}` and the
`changes` journal (written by a person, checked by the build):

```json
"changes": [{"version": "0.2.0", "from": "0.1.0", "added": [], "removed": [], "changed": [],
             "important": [], "note": "user-facing, one or two sentences"}]
```

`added`/`removed` must equal the id difference to the previous version, every step whose
`content_version` changed must be in `changed`, `important` ⊆ `added` ∪ `changed`; otherwise the
build fails.

**Canonical `content_version`.** The `options` of every situation are hashed **sorted by id**, and
`scenarios.option_ids` are sorted by id, so a permutation of options keeps the version (no repeat, no
notice). The order of the situations list and every other sequence is kept. Texts, keys, reactions,
rubrics (of the primary and of every situation, by content) and the situations themselves are in it:
editing any of them changes the version. For every step of 0.2.0 the canonical form is identical to the
former one (all quizzes list `a, b, c`), so no 0.2.0 version changed.

### 2.8 Answer version and the scenario registry

```
answer_version(situation) = sha256(canon({question, options: [{id, text, correct}] sorted by id,
                                          rubric: normalised text of the resolved rubric or "-"}))[:16]
```

Whitespace is normalised; `reaction` and the rubric status are not part of it (a reaction edit or a
rubric accepted later keeps the answer). A rubric enters by its text, not by `rubric_ref`.

`course/scenario-registry.tsv` (append-only, under git; columns `scenario_id, step, answer_version,
first_course_version, note`) pins every situation id ever released to its **step and answer**. The
build (`course-merge.py`) checks every situation of the course: an id not in the registry is new and
its row is appended; an id in the registry with another `answer_version` or **under another step**
fails the build; an id whose registry rows disagree (conflicting history) is forbidden and fails the
build. A removed situation stays in the registry, so "remove → bring back the same id with another
answer" fails, and "the same answer" keeps its old reveal. A changed question, option, key or rubric
needs a new id; moving a task to another step needs a new id. Rows are never changed or deleted
(`scripts/test-p2b.py` checks the candidate registry is a line-by-line superset of the base one).
The registry was initialised by `course-merge.py --init-registry` from every released course
version in git (0.1.0 = `ea17f9e`, 0.2.0 = `a06537d`); its header lists the commits read. An id
absent from the registry because it existed only in an unavailable history is not proof of newness.

**Fail closed.** `--init-registry` exits nonzero and writes nothing (no new file, an existing one is
never rewritten) when any mandatory release is unavailable — its `course.json` or its historical rubric
table cannot be read, or a newer commit is unreadable while finding the newest 0.2.0; the coverage report
is still printed with `unavailable`/`mandatory_unavailable`. The build trusts a registry only if its
`# Init sources:` header names every mandatory release and `unavailable: none`; otherwise it fails, so a
partial init can never admit a retired id with another answer. A complete registry works offline: the
build reads only the file. `check_registry` itself compares rows and is not a provenance check.

## 3. Lesson texts — `course/lessons/*.md`

One file per lesson (or shared by a few lessons of one topic). Plain human text, short paragraphs,
one example per idea. Headings are anchors for `text_ref`. Same language rule as §2.6.

## 4. Progress — `mentor/progress.json` in the user's workspace (schema 2)

Written **only** by `course/progress.py` (standard library, next to `kb-box/`). Mentor never edits the
file by hand: it calls the script and judges (rubric verdict, kind of evidence); the script keeps the
books. The script enforces these rules for calls made through it; it cannot stop a direct file write
*(not tested on the platform)*.

```json
{
  "schema": 2, "revision": 41, "course_version": "0.2.0",
  "nav": {"cursor": "S1.L16.s05",
          "stack": [{"kind": "notice", "notice_id": "0.2.0#added-…", "steps": ["S1.L14.s09"], "index": 0,
                     "return_to": "S1.L16.s05", "started_at": "…"}],
          "paused": null},
  "completed": ["S1.L01.s01"], "skip_reasons": {},
  "open": {"token": "…", "step": "S1.L14.s13", "content_version": "…", "scenario_id": "S1.L14.s13",
           "option_ids": ["a", "b", "c"], "scoring": true, "next_attempt": 2, "opened_at": "…",
           "display": [{"label": "a", "option_id": "a"}, {"label": "b", "option_id": "b"},
                       {"label": "c", "option_id": "c"}],
           "question": "…", "options": [{"id": "a", "text": "…", "reaction": "…"}, "…"]},
  "checks": {"S1.L14.s13": {"lifecycle": "active", "content_version": "…",
             "current": {"status": "shown", "evidence": "-", "attempt": 1}, "best_this_version": null,
             "exposure": {"S1.L14.s13": {"revealed": false, "content_version": "…"}},
             "history": [{"attempt": 1, "content_version": "…", "scenario_id": "S1.L14.s13",
                          "option_ids": ["b"], "rubric_verdict": "incorrect", "status": "shown",
                          "evidence": "-", "revealed": false, "scored": true, "origin": "runtime", "at": "…"}]}},
  "notices": [{"id": "0.2.0#added-…", "kind": "added", "version": "0.2.0", "steps": ["…"],
               "important": true, "state": "new", "later_count": 0, "note": "…"}],
  "repeat": [], "legacy": {}, "exposure": {}, "consumed_messages": [],
  "migrations": [{"id": "m1", "from": "0.1.0", "to": "0.2.0", "schema_from": 1, "source_sha256": "…",
                  "backup": "mentor/progress-backups/0.1.0-3fa9c2d1.json", "at": "…"}],
  "updated": "…"
}
```

| Field | Rule |
|---|---|
| `revision` | +1 on every write; commands without an open expectation pass `--revision` (a repeated call fails) |
| `nav.cursor` | main course position: a step id or `finish` |
| `nav.stack` | detours (a notice, a lesson taken from a question); while not empty the current step is the top frame's `steps[index]`; finishing the frame returns to `return_to` |
| `nav.paused` | `{at, resume_target, following}` set by a checkpoint `pause`; only `resume` clears it (a detour does not). `following` lists the next step ids so a migration can keep a valid target or move past a removed one |
| `open` | the one open expectation of a shown check; a record must carry its `token` and `next_attempt`. It **freezes** the shown situation: `display` (label → option id, label = position), and for a quiz `question` and `options` (text, reaction) at the moment of opening. A repeated `open` of the same expectation returns the frozen copy, never one recomputed from the current array |
| `superseded_opens` | expectations opened before P2b (no `display`), closed by `migrate`: no attempt, no repeat, no notice; their token is dead |
| `checks[id]` | `lifecycle` (`active` / `needs_recheck`) ⟂ attempt `status` (`shown` / `skipped` / `said_done` / `confirmed`); `best_this_version` is the score of the current content only |
| `exposure` | identity `(step, scenario_id)`, **without a version**: a revealed situation is never scored again while its id is the same, even when the step's `content_version` changes (a reaction edit, a new situation). Kept per check and in the top-level ledger `exposure[step][scenario]`, rebuilt from checks and `legacy` on migrate, so it survives a step removed and brought back. Attempts are still counted per `content_version` |
| `consumed_messages` | every `--message-id` ever recorded; kept for the life of the file (never truncated), a repeated id is refused |
| `origin` | `runtime` / `user_form` ([Сделал]) / `legacy_unknown` (schema 1) |
| history entry, since 0.3.0 | `record` and `skip` add `course_version` and `release_id` (the course version and `course.json` `release_id`, else null, **at the moment of the attempt**), `shown_order` (option ids in the frozen `display` order for a quiz, else null) and `attempt_uid` (uuid4, generated once; the answer event's identity). Optional fields: the schema number stays 2, older entries are never rewritten. Reading rule: an entry with `course_version` is `recorded`; an entry without it gets its version only from `migrations[]` — strictly earlier than a migration whose `from` is a version → that `from` (the nearest such migration), `reconstructed`; anything else (no time, equal time, no later migration) → `null`, `unknown`. `content_version` never decides the course version (one CV can live in two versions). Entries without `attempt_uid` are shown by `export-feedback` but never sent |
| `notices` | `kind` `added` / `correction`; `state` `new` / `later` / `started` / `done` / `in_repeat` |
| `repeat` | checks to redo ("Повторить"): content changed, or a notice postponed 3 times |
| `legacy` | append-only lists of original records: every schema-1 record verbatim, the rest of the schema-1 file under `_file`, and every record of a step removed from the course. A schema-1 quiz entry carries `option_basis`: its letter is read as the option id, because in 0.1.0–0.2.0 every quiz lists `a, b, c` (checked on those snapshots) |

**Scoring.** `confirmed` only when the code computes `scoring = step eligible AND the situation is not
revealed AND the situation's own rubric exists and is accepted` (§2.3, §2.7), with
`rubric_verdict = correct` and real `evidence`; `verified_artifact` needs an artifact reference naming
the step's own `check.method` and `check.detail` and what was observed. A non-scoring check records
only `shown` or `skipped`. `said_done` is the user's word, never a score. Three wrong answers on a
scored situation reveal it. `open` takes the first situation in show priority that is not revealed;
`record` accepts only an option id of that situation and judges it by **that** situation's key.

**Label check.** Under a frozen `display`, `record` needs `--label <the label the learner chose>`
together with each `--option`, and refuses a pair where `display[label] ≠ option`. This proves that
the label and the id are **consistent**; that the learner chose that label is Mentor's word (and the
platform's, if its form returns the button text) — **not** a guarantee of this script.

**Migrate output.** Besides `notices`, `rechecks`, `legacy_added`, `backup`: `version_changed` and
`changed_done` / `changed_done_steps` — the steps changed by this update (content version changed, or
listed in `changes[].changed`) that the user had done (completed or attempted). Mentor says only «Курс
обновился: изменено N шагов, которые ты проходил»; the repeat schedule is unchanged.

**Feedback files** (contract: `course/EVENT-SCHEMA.md`, data set `course-feedback-v1`), next to
`progress.json`, all written under the same lock: `events.jsonl` (append-only `answer` / `remark`
events), `consent.jsonl` (append-only decisions), `identity.json` + `identity.json.bak` (private:
collector id, registration), `outbox-state.json` (delivery cache). `record`/`skip` commit
`progress.json` first and then append the answer line; a missing line is rebuilt from history before
every flush and by `doctor`. `remark` (one JSON object on stdin) never reads or writes `progress.json`.
`consent`, `flush --endpoint URL` (the only network command, run explicitly as its own call; only with
`granted` consent and an https endpoint from `GROKBOT_FEEDBACK_URL` or `feedback.json` next to
`course.json`, which `--endpoint` must name; stdout statuses and exit codes: EVENT-SCHEMA §3),
`export-feedback` (read-only JSON lines), `doctor` (torn last lines, identity, missing events). No other
command touches the network; `record`/`skip` print `attempt_uid` and `event_id`. After the network call it waits up to 10 s for the lock to save the answer; if it
cannot, events stay pending (re-sent, answered `duplicate`), and a lost registration answer only means the
next flush registers again (the unused server installation holds no events and is harmless). `where` shows `feedback: {recipient, endpoint, consent}`. None of these files is committed by
Mentor except as listed in §3 of MENTOR-RUNTIME (they are not).

**Migration** (`progress.py migrate`, first call of every course session, idempotent): lock
(`mentor/.progress.lock`, owner token; busy = error, no unlock by age) → immutable byte copy
`mentor/progress-backups/<version>-<sha8>.json` → new file. Schema 1 records go to `legacy` whole and
give no score; every schema-1 quiz record marks its scenario revealed. Steps removed from the course
move to `legacy`, a removed `cursor` becomes the first step after the last surviving `completed`. From
the `changes` journal, added steps before the cursor that are not done and changed steps the user
already did become notices; checks whose `content_version` changed lose their score and go to
`repeat`. An open expectation without `display` (opened before P2b) is closed as `superseded`: no
attempt, no repeat, no notice; its token is refused afterwards and the next `open` shows the step
again with a frozen layout. Corrupt JSON, a newer schema or an older course version is an error with
nothing written.
`progress.py rollback --to <migration id>` (operator only) saves the live file as a new copy and
restores the copy byte for byte.

**Saving to history.** Mentor commits `mentor/` at the end of a lesson, at a checkpoint and when the
user stops, with the usual commit rules: author `GrokBotCEO bots`, message ends with `Bot: Mentor`.
Progress is Mentor's own bookkeeping, so no `(yes: "...")` line *(not tested)*. Backups and the lock
are not committed.

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
