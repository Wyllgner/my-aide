-- Esquema inicial. Ver ARQUITETURA.md seção 7.4.

CREATE TABLE tasks (
    id              INTEGER PRIMARY KEY,
    title           TEXT    NOT NULL,
    notes           TEXT,
    status          TEXT    NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'done', 'dropped')),
    priority        INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 4),
    project         TEXT,
    tags            TEXT,
    due_at          TEXT,
    recurrence      TEXT,
    snooze_count    INTEGER NOT NULL DEFAULT 0,
    last_touched_at TEXT,
    private         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT,
    deleted_at      TEXT
);
CREATE INDEX idx_tasks_due    ON tasks (due_at)   WHERE deleted_at IS NULL;
CREATE INDEX idx_tasks_status ON tasks (status)   WHERE deleted_at IS NULL;

CREATE TABLE events (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    start_at    TEXT NOT NULL,
    end_at      TEXT,
    location    TEXT,
    source      TEXT NOT NULL DEFAULT 'local',
    external_id TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at  TEXT
);
CREATE INDEX idx_events_start ON events (start_at) WHERE deleted_at IS NULL;

CREATE TABLE reminders (
    id           INTEGER PRIMARY KEY,
    text         TEXT NOT NULL,
    fire_at      TEXT NOT NULL,
    repeat_rule  TEXT,
    status       TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'delivered', 'cancelled')),
    delivered_at TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_reminders_fire ON reminders (fire_at) WHERE status = 'pending';

CREATE TABLE notes (
    id         INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
    path       TEXT NOT NULL UNIQUE,
    tags       TEXT,
    private    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE TABLE memory (
    id            INTEGER PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('profile', 'episodic')),
    key           TEXT NOT NULL,
    value         TEXT NOT NULL,
    confidence    REAL NOT NULL DEFAULT 1.0,
    private       INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    superseded_by INTEGER REFERENCES memory (id)
);
CREATE INDEX idx_memory_key ON memory (kind, key) WHERE superseded_by IS NULL;

CREATE TABLE people (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    relation        TEXT,
    last_contact_at TEXT,
    cadence_days    INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE work_orders (
    id             INTEGER PRIMARY KEY,
    goal           TEXT NOT NULL,
    context        TEXT,
    refs_json      TEXT,
    done_criteria  TEXT,
    priority       INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 4),
    status         TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'claimed', 'done', 'dropped')),
    claimed_by     TEXT,
    claimed_at     TEXT,
    result_summary TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at   TEXT
);
CREATE INDEX idx_work_orders_status ON work_orders (status);

CREATE TABLE messages (
    id         INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content    TEXT,
    tool_calls TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_messages_session ON messages (session_id, id);

CREATE TABLE audit (
    id             INTEGER PRIMARY KEY,
    ts             TEXT NOT NULL DEFAULT (datetime('now')),
    actor          TEXT NOT NULL,
    tool           TEXT NOT NULL,
    args_json      TEXT,
    result_summary TEXT,
    ok             INTEGER NOT NULL DEFAULT 1
);

-- Uso de LLM, para saber quanto o assessor custa por dia.
CREATE TABLE llm_usage (
    id            INTEGER PRIMARY KEY,
    ts            TEXT NOT NULL DEFAULT (datetime('now')),
    model         TEXT NOT NULL,
    purpose       TEXT,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms    INTEGER
);
