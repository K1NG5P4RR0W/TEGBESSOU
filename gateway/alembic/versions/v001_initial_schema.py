"""V001 — schéma public initial (§11).

Crée les 12 tables du schéma public + le trigger append-only de l'audit.

Revision ID: v001
Revises:
"""

from collections.abc import Iterator

from alembic import op

revision = "v001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SQL = r"""
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    totp_secret   BYTEA NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin','lead','analyst','viewer')),
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE module_registry (
    id                 TEXT PRIMARY KEY,
    agent              TEXT NOT NULL,
    title              TEXT NOT NULL,
    ordering           INT NOT NULL,
    version            TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','deprecated','disabled')),
    enabled_by_default BOOLEAN NOT NULL DEFAULT true,
    config_json        JSONB NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE engagements (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    mode                TEXT NOT NULL CHECK (mode IN ('pentest','bug_bounty','ctf','audit_code')),
    client              TEXT,
    schema_name         TEXT NOT NULL UNIQUE,
    status              TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','paused','closed')),
    current_phase       TEXT,
    methodology_version TEXT,
    owner_id            UUID NOT NULL REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at           TIMESTAMPTZ
);

CREATE TABLE authorizations (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id  UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    source_kind    TEXT NOT NULL CHECK (source_kind IN ('sow','program_url','program_text')),
    document_name  TEXT,
    program_url    TEXT,
    rules_text_ref TEXT,
    parsed_rules   JSONB,
    content_hash   TEXT NOT NULL,
    storage_ref    TEXT,
    validated_by   UUID REFERENCES users(id),
    validated_at   TIMESTAMPTZ,
    UNIQUE (engagement_id)
);

CREATE TABLE forbidden_techniques (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id  UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    label          TEXT NOT NULL,
    blocks_module  TEXT REFERENCES module_registry(id),
    source         TEXT NOT NULL DEFAULT 'program'
);

CREATE TABLE scope_entries (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id  UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    kind           TEXT NOT NULL CHECK (kind IN ('domain','ip','cidr','contract')),
    value          TEXT NOT NULL,
    disposition    TEXT NOT NULL CHECK (disposition IN ('in_scope','out_of_scope','exclusion')),
    chain          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE traffic_configs (
    engagement_id   UUID PRIMARY KEY REFERENCES engagements(id) ON DELETE CASCADE,
    max_rps         NUMERIC NOT NULL DEFAULT 5,
    max_concurrency INT NOT NULL DEFAULT 3,
    delay_ms        INT NOT NULL DEFAULT 0,
    allowed_window  TSRANGE
);

CREATE TABLE custom_headers (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id  UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    header_key     TEXT NOT NULL,
    header_value   TEXT NOT NULL
);

CREATE TABLE llm_configs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_level       TEXT NOT NULL CHECK (scope_level IN ('global','engagement','user')),
    engagement_id     UUID REFERENCES engagements(id) ON DELETE CASCADE,
    user_id           UUID REFERENCES users(id) ON DELETE CASCADE,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    api_key_enc       BYTEA,
    key_fingerprint   TEXT,
    temperature       NUMERIC NOT NULL DEFAULT 0.2,
    budget_cap_usd    NUMERIC,
    fallback_provider TEXT
);

CREATE TABLE engagement_modules (
    engagement_id UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    module_id     TEXT NOT NULL REFERENCES module_registry(id),
    enabled       BOOLEAN NOT NULL,
    PRIMARY KEY (engagement_id, module_id)
);

CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_id      UUID REFERENCES users(id),
    engagement_id UUID,
    action        TEXT NOT NULL,
    target        TEXT,
    params_json   JSONB,
    prev_hash     TEXT NOT NULL,
    entry_hash    TEXT NOT NULL
);

CREATE TABLE llm_usage (
    id            BIGSERIAL PRIMARY KEY,
    engagement_id UUID NOT NULL,
    agent         TEXT NOT NULL,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INT NOT NULL,
    output_tokens INT NOT NULL,
    cost_usd      NUMERIC NOT NULL,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION audit_log_no_mutate() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log est append-only : % interdit', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_mutate_trg
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_no_mutate();
"""

_DROP_ORDER = [
    "llm_usage",
    "audit_log",
    "engagement_modules",
    "llm_configs",
    "custom_headers",
    "traffic_configs",
    "scope_entries",
    "forbidden_techniques",
    "authorizations",
    "engagements",
    "module_registry",
    "users",
]


def _split_statements(sql: str) -> Iterator[str]:
    """Découpe le SQL en instructions, en respectant les blocs $$...$$."""
    buf: list[str] = []
    dollar_open = False
    for line in sql.splitlines():
        buf.append(line)
        if line.count("$$") % 2 == 1:
            dollar_open = not dollar_open
        if not dollar_open and line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt:
                yield stmt
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        yield tail


def upgrade() -> None:
    for stmt in _split_statements(SCHEMA_SQL):
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_mutate_trg ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_no_mutate()")
    for table in _DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
