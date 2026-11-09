-- Stats database schema for reader workflows (SQLite)
--
-- This file is the ONLY source of DDL for stats.db. scripts/reading-dedup-sort.py
-- applies it (all statements are idempotent) and refuses to run on a database whose
-- structure differs; tests load this exact file. Do not copy these CREATE statements
-- anywhere else.
--
-- Canonical field names (contract):
--   platform  - where a post comes from: 'x' or 'telegram'. This is the ONLY name for
--               this field in every table, prompt, report and script. The old name
--               `source` is a legacy alias: reading-dedup-sort.py accepts it on JSON
--               input and converts it to `platform`; it is never a column.
--   post_id   - the post ID on that platform (string). Legacy JSON alias: `id`.
--   user_id   - author ID on that platform (string). Legacy JSON alias: `author`.
--   reader    - which reader bot ran the cycle: 'x' or 'telegram'.
--
-- Writers (single writer per table, all through reading-dedup-sort.py with
-- parameterized queries; prompts pass structured JSON, never hand-written SQL):
--   cycles, posts, registry  <- `record-stats`
--   seen_texts               <- `mark-seen`, run only AFTER the digest was delivered,
--                               so a failure in a later stage never loses a post
--   bot_accounts             <- reader prompt (bot detection), reads seen_texts only
--
-- Upgrading an older database (seen_texts keyed without platform, or posts.source):
--   python3 scripts/reading-dedup-sort.py migrate --db <stats.db>

-- Reading cycles tracking. One row per reader run; (reader, started_at) identifies a
-- run, so recording the same run twice updates it instead of duplicating it.
CREATE TABLE IF NOT EXISTS cycles (
    cycle_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reader TEXT NOT NULL, -- 'x' or 'telegram'
    started_at TEXT NOT NULL, -- ISO8601 timestamp with zone
    completed_at TEXT,
    status TEXT DEFAULT 'running', -- running, completed, failed
    posts_read INTEGER DEFAULT 0,
    posts_selected INTEGER DEFAULT 0
);

-- Posts scoring and tracking
CREATE TABLE IF NOT EXISTS posts (
    platform TEXT NOT NULL, -- 'x' or 'telegram' (canonical name, never `source`)
    post_id TEXT NOT NULL,
    channel TEXT, -- author handle or telegram channel
    text TEXT NOT NULL,
    score INTEGER, -- 1-5 stars (final score, after full article if fetched)
    score_teaser INTEGER, -- score before article fetch
    fulltext TEXT, -- 'full', 'teaser', 'error'
    registry_key TEXT, -- '<platform>:<post_id>' when the post is in registry
    orig_id TEXT, -- original platform ID
    cycle_no INTEGER,
    created_at TEXT NOT NULL,
    PRIMARY KEY (platform, post_id),
    FOREIGN KEY (cycle_no) REFERENCES cycles(cycle_id)
);

-- Shared selection registry (14 day window), written for selected posts
CREATE TABLE IF NOT EXISTS registry (
    registry_key TEXT PRIMARY KEY, -- '<platform>:<post_id>'
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    expires_at TEXT NOT NULL, -- first_seen + 14 days
    FOREIGN KEY (platform, post_id) REFERENCES posts(platform, post_id)
);

-- Seen content keys for deduplication (platform-aware).
-- text_hash = sha1 of the post text lowercased, with tokens starting with http:// or
-- https:// removed and whitespace collapsed. If nothing remains (a post that is only
-- links), the key is built from the normalized URLs instead; if there are no URLs
-- either, from platform and post_id. Empty text is never used as a shared key.
CREATE TABLE IF NOT EXISTS seen_texts (
    text_hash TEXT NOT NULL,
    user_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    PRIMARY KEY (text_hash, user_id, platform)
);

-- Bot accounts tracking
CREATE TABLE IF NOT EXISTS bot_accounts (
    user_id TEXT PRIMARY KEY,
    handle TEXT,
    repeats INTEGER DEFAULT 1,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    sample_post_ids TEXT, -- JSON array
    status TEXT DEFAULT 'new' -- 'new', 'listed', 'blocked'
);

-- Agent metrics (funnel tracking)
CREATE TABLE IF NOT EXISTS agent_metrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_no INTEGER NOT NULL,
    reader TEXT NOT NULL,
    metric_type TEXT NOT NULL, -- 'read', 'selected', 'routed', 'processed'
    count INTEGER DEFAULT 0,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (cycle_no) REFERENCES cycles(cycle_id)
);

-- Indexes for common queries
CREATE UNIQUE INDEX IF NOT EXISTS idx_cycles_reader_started ON cycles(reader, started_at);
CREATE INDEX IF NOT EXISTS idx_posts_cycle ON posts(cycle_no);
CREATE INDEX IF NOT EXISTS idx_posts_score ON posts(score);
CREATE INDEX IF NOT EXISTS idx_registry_expires ON registry(expires_at);
CREATE INDEX IF NOT EXISTS idx_seen_texts_post ON seen_texts(platform, post_id);
CREATE INDEX IF NOT EXISTS idx_bot_accounts_status ON bot_accounts(status);
CREATE INDEX IF NOT EXISTS idx_agent_metrics_cycle ON agent_metrics(cycle_no);
