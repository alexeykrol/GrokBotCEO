# Course feedback events — contract v1 (course-feedback-v1) and v2 (course-feedback-v2, §5)

Source of truth for both sides: the student-side client (`release/course/progress.py`) and the receiver
(`services/feedback-receiver`, endpoint `POST /v1/course-event`). Plan: `docs/design/release-0.3.0-plan.md`
(main repo), sections C2–C4, C6. Any change here = new contract version. §1–§4 are v1 and stay readable;
§5 lists only what v2 changes (design: `docs/design/feedback-protocol-v2.md`).

## 1. Local files (next to `progress.json`, in `mentor/`)

All writes happen under the same Store lock as `progress.json`.

| File | Kind | Content |
|---|---|---|
| `events.jsonl` | append-only, one JSON object per line, never rewritten | `answer` and `remark` events (§2) |
| `consent.jsonl` | append-only | `{"at", "decision": "granted"\|"revoked", "scope": {"data_set": "course-feedback-v1", "recipient": "<host>", "course_major": "0"}, "course_version"}` |
| `identity.json` | written once atomically (tmp + fsync + rename) plus `identity.json.bak`; PRIVATE (never exported, never in a package) | `{"version": 1, "collector_id": str, "install_id": str\|null, "send_token": str\|null, "created_at"}` — durable identity and registration; updated only to add the registration once |
| `outbox-state.json` | rewritten atomically; a rebuildable CACHE | `{"version": 1, "delivered": {"<event id>": {"at", "result": "accepted"\|"duplicate"}}, "rejected": {"<event id>": {"at", "reason"}}}` |

- A torn last line of a `.jsonl` file (crash during append) is ignored on read and reported by `doctor`;
  complete lines are never modified.
- Missing or unreadable `outbox-state.json` (cache only) → treated as empty; events are re-sent under the
  SAME identity and credentials; the server answers `duplicate` for identical payloads (no second row).
- Bootstrap (Codex 0e291f8d): `identity.json` is created on first r030 use when there is NO evidence of
  prior r030 identity — evidence = any of `events.jsonl`, `consent.jsonl`, `outbox-state.json`,
  `identity.json.bak`, or a history entry with `attempt_uid`. Pre-r030 history alone is not evidence;
  such students initialise normally (their old entries are never sent). Order: check evidence → create
  identity atomically → only then write the first event.
- Missing or unreadable `identity.json` WITH such evidence → restore from
  `identity.json.bak` only if it is valid; otherwise `doctor` reports `identity_lost`, network sending
  stops, and NO new collector/registration is created automatically. Events and progress are kept;
  grading is unaffected. Recovery = restoring a verified snapshot, which continues the same installation.
- Effective consent = the last complete line of `consent.jsonl` whose scope matches the current
  `data_set` and `recipient`. No such line, or `revoked` → nothing is sent.

## 2. Event object

Events are local and immutable: they never contain `install_id`, `send_token` or `collector_id`. The server-side installation is bound only in the transport envelope.

Common fields (all required unless marked):

| Field | Type | Rule |
|---|---|---|
| `id` | string, 32 lowercase hex | `sha256(collector_id + "\|" + source + "\|" + record_kind)[:32]` (UTF-8, fields joined by `|`, no other encoding), computed by the client BEFORE the line is written. `collector_id` = random 32-hex created once before the first event and stored in `identity.json` (never sent, never regenerated while events exist; restored only from a saved snapshot). Ids never change on registration or re-registration. |
| `type` | `"answer"` \| `"remark"` | |
| `course_version` | string ≤32 or null | the course version at the moment of the event (recorded) |
| `release_id` | string ≤64 or null | RC tag of the installed release, from `course.json` `release_id` if present |
| `version_origin` | `"recorded"` \| `"reconstructed"` \| `"unknown"` | new events are always `recorded` |
| `at` | ISO-8601 UTC string | |

`answer` (one per recorded attempt of a quiz/exercise; `source` = `"answer-uid:" + attempt_uid`, where `attempt_uid` is a uuid4 generated once when `record` commits the attempt and stored in that history entry; rebuild always uses the stored value. A displayed `attempt` counter is NOT an identity: it restarts per content_version and per scenario (primary vs `.b`). History entries without `attempt_uid` (written before r030) are never sent; they appear only in `export-feedback` with `version_origin`. Re-running `record` for an already consumed input message creates no new attempt and no new event):

| Field | Type |
|---|---|
| `step` | string ≤64 |
| `scenario_id` | string ≤96 or null |
| `option_ids` | list of ≤3 strings ≤32 (chosen option ids, stable under permutation); `[]` for exercises |
| `shown_order` | list of ≤3 strings ≤32 or null (option ids in the order shown) |
| `status` | string ≤24 (as stored in history) |
| `attempt` | int ≥1 |
| `revealed` | bool |
| `evidence_class` | string ≤24 or null (exercises; never the artifact content) |

`remark` (`source` = `"remark-uuid:" + <uuid4 generated by the client once, when the remark is written>` — ALWAYS, whether or not `source_msg` is present; Codex 6e9baebd):

Platform note (Grok 063a7bb8): a stable machine-readable message id is NOT confirmed — in 1:1 chats the
model sees a short per-conversation address as text, in rooms nothing; the same address can occur in two
conversations. So `source_msg` is metadata only (visible address or null) and never part of identity.
Retry idempotency: `progress.py remark` prints the event `id` it wrote; the caller may pass that `id`
back (`"event_id"` in the stdin JSON) to retry the same operation — same id + same payload → no new line,
same id + different payload → error `conflict`, nothing written. A call without `event_id` is always a
new event. Possible duplicates (same installation + step + kind + normalised text within 10 minutes) are
FLAGGED `possible_duplicate` in the summary only — never removed, never identity, never grading.
Text + minute is never an identity key.
Declared coverage limit (Codex 010990ef): without `source_msg`, if the model records the same student
message twice, these are two events — automatic dedup of the original message is NOT guaranteed; the
`possible_duplicate` flag only helps analysis. A stored `source_msg` is unverified metadata with
per-conversation scope.

| Field | Type |
|---|---|
| `source_msg` | string ≤128 or null — visible address of the student's message if the runtime shows one |
| `scope` | `"step"` \| `"course"` |
| `step` | string ≤64 or null (required when scope = step) |
| `scenario_id` | string ≤96 or null |
| `kind` | `"unclear"` \| `"wrong"` \| `"other"` |
| `text` | string 1..1000 chars, after client masking (§4) |
| `parent_id` | 32-hex id of an earlier remark or null (follow-up of a clarifying dialogue) |

Unknown fields are rejected by the server.

Every string (keys, values, list items) must be valid Unicode; a string that cannot be strict-UTF-8 encoded (e.g. an unpaired surrogate escape `\ud800`) is rejected per event as `field:<name>` (bad key → `schema`; an invalid id is echoed as `null`) before hashing or storage, and the rest of the batch is processed. In the envelope it is a 400 with nothing written. Valid non-BMP characters are stored byte-identically.

## 3. Transport

Request: `POST /v1/course-event`, header `Authorization: Bearer <send_token>`, JSON `{"install_id": "<from /v1/register>", "events": [<≤50 events>]}`,
body UTF-8 JSON (`ensure_ascii=False`) ≤ 128 KiB — the client splits batches by encoded size, HTTPS only (client refuses plain http except `127.0.0.1`/`localhost` for tests).

Response 200: `{"accepted": [id...], "duplicate": [id...], "rejected": [{"id", "reason"}...]}`.
Every submitted id appears in exactly one list. 4xx for a malformed envelope (no per-event lists) →
client keeps all events pending. 5xx / timeout / network error → all pending.

- Server: unique key `(install_id, id)`, where install_id comes from the verified token; `accepted` only after the row is committed; a repeated key with an IDENTICAL payload (canonical JSON hash) → `duplicate`; a repeated key with a DIFFERENT payload → rejected `conflict` (client records it as rejected, never as delivered)
  (no second row, no update of the stored row).
- Server rejects per event (not the whole batch) on schema violation; `reason` is a short code
  (`schema`, `field:<name>`, `too_long`, `unknown_install`); envelope errors are whole-request and nothing is written: 401 missing/malformed token, 403 `forbidden` (unknown token), 403 `install_mismatch` (body install_id is not the token's installation, incl. unregistered), 413 oversize, 400 malformed or empty `events`. So `unknown_install` is never a per-event reason. Nullable fields may be omitted (treated as null).
- Client marks delivered only ids present in `accepted` or `duplicate`; `rejected` are recorded in
  `outbox-state.json` and never re-sent automatically; everything else stays pending.
- Client deadline: ONE hard overall deadline of 10 s per request, counted from the start of the call and
  covering every phase — DNS, connect, TLS handshake, sending, response headers and the whole body, also
  after the response has detached from its connection (HTTP/1.0, `Connection: close`). Mechanism: the request
  runs in one short-lived child process (`python -I -B -c`, stdlib; url, body and token passed on stdin, never
  in argv); the parent waits for it at most until the deadline, then terminates it (0.5 s grace) and kills it,
  so the call returns within deadline + ≤1 s with no child, thread or connection left and no request can be
  sent after it. This is a transport failure — events stay pending, nothing is marked delivered or rejected,
  no registration is stored from a partial answer, no retry. At most 1 request per `flush` call (register OR
  one batch), so the network part of a flush is ≤10 s; saving the answer then waits at most 10 s more for the
  Store lock.
- Explicit flush (rc2): `flush` is the ONLY command that touches the network, and it runs only when called
  on its own (`progress.py --kb-home mentor flush --endpoint <configured endpoint>`). Every other command
  (migrate, where, open, record, skip, advance, checkpoint, resume, notice, lesson, remark, consent, doctor,
  export-feedback) is local: it never spawns the request child, whatever the endpoint and consent. The command
  names its destination: `--endpoint` is required when an endpoint is configured and must equal it after
  normalisation (scheme and host lower-case, default port and trailing `/` dropped, path kept); otherwise the
  flush is `refused` and does nothing at all. `where` shows the configured value as `feedback.endpoint`.
- Flush stdout is one JSON object: `status`, `reason`, `sent`, `accepted`, `duplicate`, `rejected`,
  `pending` (events still to send), `rebuilt`; plus `http_status` / `error` / `detail` when relevant.

  | status | reason | exit | meaning for the caller |
  |---|---|---|---|
  | `delivered` | – | 0 | one batch sent and answered; `pending` > 0 means the next flush sends more |
  | `nothing_pending` | – | 0 | nothing to send |
  | `registered` | – | 0 | the installation was registered (that was the one request); events go next flush |
  | `pending` | `deadline`, `transport`, `http`, `busy`, `oversize`, `register_discarded` | 0 | nothing delivered now; all stays on disk for a later explicit flush |
  | `skipped` | `no_endpoint`, `endpoint_refused`, `no_consent`, `identity_lost` | 0 | not configured or not allowed; no request |
  | `refused` | `endpoint_required`, `endpoint_mismatch` | 3 | the command is wrong; nothing read, written or sent |

  Exit 2 (`progress: ERROR` on stderr, no JSON) only for a broken installation. No status is retried
  inside the call; the caller does not retry either — the next scheduled flush picks up what is pending.
- `install_id` and a per-install `send_token` (random ≥32 bytes, url-safe) are obtained from `POST /v1/register`
  on the first flush after consent and stored in `identity.json`. The server stores only
  `sha256(send_token)` and authenticates the request by token; the envelope `install_id` must match the
  token's installation, else 403 and nothing is written. Dedup key is `(install_id, id)` (see above): another
  installation cannot mark or overwrite events of the first. The token is sent only to the configured
  HTTPS host; no redirects are followed, no fallback to another host or to http. Older registrations
  without a token cannot post course events. The admin secret exists only in the server environment.

## 3a. Crash safety (record ↔ events)

- `record` first commits the answer to `progress.json` atomically, with everything needed to rebuild
  the event (stable source, versions, scenario, option_ids, shown_order). Only then the `answer` line is
  appended (append + fsync).
- Before every flush (and in `doctor`), missing `answer` events are rebuilt idempotently from committed
  history; only committed answers are ever sent. A failed `record` produces no event. `record` / `skip`
  print the committed attempt's `attempt_uid` and its `event_id` (null under `identity_lost`); `remark`
  prints its `id`. All of it is on disk before any flush.
- `remark` is append + fsync and never touches grading.
- A torn trailing line is truncated to the last complete line (complete earlier lines are never
  dropped); the truncated bytes are saved to `events.torn-<ts>` for inspection.
- `record` never flushes, so delivery cannot change its exit status or output; a failed or skipped flush
  leaves `progress.json` (history, open question, verdict) untouched and delivery simply stays pending.

## 4. Text handling

Client (before writing the line): masks known secret formats to `[скрыто]` — provider keys
(`sk-…`, `xai-…`, `ghp_…`, `github_pat_…`, `AKIA…`), JWT-like `xxx.yyy.zzz`, hex/base64 runs ≥32,
e-mail addresses, phone numbers (≥9 digits). Declared limitation: free text may contain secrets the
filter does not recognise.

Server: stores text as data only; never executes it, never builds paths/commands from it; flags (does
not drop) text containing HTML/script tags, URLs, control characters, or leading `= + - @` (CSV
formula). Flag = `flagged` column with reason codes; flagged rows are shown in quarantine in the admin
summary. Admin HTML output is escaped; CSV export prefixes formula-leading cells with `'`.

## 5. Contract v2 (course-feedback-v2)

Everything in §1–§4 holds unless changed here. The contract in force for a recipient is the `data_set` of
its last consent line: a v1 line keeps the v1 behaviour (answers and remarks, no envelope `contract`).

**Sent data.** `remark` events only. `answer` events are still written locally (§3a) and exported, but a v2
flush never sends them. Only the text the user wrote as a remark about the course is sent: never the rest of
the chat, never quiz answers.

**Consent** (`consent.jsonl`, scope `data_set: "course-feedback-v2"`). Decisions:

| decision | written by | rule |
|---|---|---|
| `granted_at_install` | the install, `consent --decision granted_at_install [--participant-key K]`; also an update that installs a release whose accepted terms notice says remarks are sent (UPDATE.md step 11, no key) | only when the recipient has no consent line yet (a re-install or update never overrides a decision) |
| `acknowledged` | Mentor, the course-start notice answered («ок» or going on) | once; never after `revoked` (it does not resume sending) |
| `revoked` | «не отправляй» | stops sending at once |
| `granted` | «снова отправляй» | resumes |

`revoked` / `granted` keep the data set already in force for the recipient (none yet → v1, as before).
Sending is allowed under `granted_at_install`, `acknowledged`, `granted`. `--recipient` defaults to the
configured endpoint's host. `where.feedback` adds, for v2 only: `data_set`, `notice_due` (consent at install,
notice not yet answered, not stopped) and `queued`.

**Key file** — `~/.grokbotceo/course.env` (override: env `GROKBOT_COURSE_ENV`), outside `mentor/`, so
it survives updates. Lines `NAME=value`: `GROKBOT_INSTALL_ID`, `GROKBOT_SEND_TOKEN`, `GROKBOT_PARTICIPANT_KEY`
(the per-person key from the install link `/i/<token>`; stored only, not sent in v2). Created with mode 600
(directory 700), tmp + fsync + rename; unknown or malformed lines are ignored. No command ever prints the token
or the key. Under v2 the key file is the credential store: a flush uses its install id and token; an earlier
registration found only in `identity.json` is copied there once. A key file that cannot be written is a note
(`key_file: "failed"`), not an error; sending then goes on from `identity.json`. v1 never touches the key file.

**Registration at install.** The install runs `consent --decision granted_at_install`, then one
`flush --endpoint <configured endpoint>`: with no credentials this flush is the registration (`registered`,
`key_file`), so the first remark is not spent registering. If it failed, the first remark's flush registers
and the remark goes with the next flush. An update to such a release from an install with no consent line
does the same, gated by `update-plan.py feedback` (UPDATE.md step 11).

**Flush after each remark.** Mentor runs the flush right after every `remark` (and once at session start when
`queued` > 0). Envelope `{"install_id", "events", "contract": "course-feedback-v2"}`. The v2 flush summary adds
`data_set` and `delivered_ids` (ids marked delivered by this call: `accepted` or `duplicate`); Mentor thanks
only when the remark's id is in it. The one-request-per-flush rule, the endpoint check, the deadline and every
status of §3 are unchanged; the flush stays the only command that touches the network.

**Queue.** A failed send (non-2xx, timeout, transport, busy) leaves the remark in the local queue and the next
flush resends it. The queue is not a second file: `events.jsonl` holds every remark before any send, and
`outbox-state.json` marks what was delivered or rejected; queued = remark lines in neither.
`progress.py queue` prints `{"queued", "ids"}` (never text). Rejected remarks are not resent (§3).

**Held remarks** (tech-requirements 22d). A remark written while the v2 decision in force is `revoked` gets
`"held": true` in its local line when it is written, and `remark` prints `"held": true`. A held remark is never
sent: no flush picks it, `queue` and `where.feedback.queued` do not count it, and «снова отправляй» (`granted`)
covers only remarks written after it. The field never leaves the computer.

**Installation ID** (22h). `progress.py whoami` prints `{"install_id": <id or null>}` from the key file, else
from `identity.json` — never the send token or the participant key. Mentor shows it on «покажи мой ID».

**Receiver.** The envelope field `contract` is optional: absent or `"course-feedback-v1"` → v1;
`"course-feedback-v2"` → remarks only, any other type rejected per event as `field:type`; any other value →
400 `validation` (`field: contract`), nothing written.

Not in v2 yet: the fallback `GET /f/<key>?t=` (design §1) — not built.
