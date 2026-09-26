-- Schema for the Agentic AI platform. Idempotent: safe to run on every startup.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------- Auth ----------
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Unstructured data (RAG) ----------
CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    filename    TEXT UNIQUE NOT NULL,
    title       TEXT,
    checksum    TEXT NOT NULL,
    num_pages   INT NOT NULL DEFAULT 0,
    num_chunks  INT NOT NULL DEFAULT 0,
    uploaded_by TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The embedding dimension must match EMBEDDING_DIM (768 = nomic-embed-text).
CREATE TABLE IF NOT EXISTS document_chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    page        INT,
    content     TEXT NOT NULL,
    embedding   vector(768) NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- ---------- Structured data (SQL tool) ----------
CREATE TABLE IF NOT EXISTS departments (
    id        SERIAL PRIMARY KEY,
    name      TEXT UNIQUE NOT NULL,
    location  TEXT NOT NULL,
    budget    NUMERIC(14, 2) NOT NULL,
    head      TEXT
);

CREATE TABLE IF NOT EXISTS employees (
    id               SERIAL PRIMARY KEY,
    name             TEXT NOT NULL,
    department       TEXT NOT NULL REFERENCES departments(name),
    role             TEXT NOT NULL,
    salary           NUMERIC(12, 2) NOT NULL,
    location         TEXT NOT NULL,
    experience_years INT NOT NULL,
    hire_date        DATE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_employees_department ON employees(department);

-- ---------- Conversations (durable audit trail; Redis holds hot state) ----------
CREATE TABLE IF NOT EXISTS chat_sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username   TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    route       TEXT,
    latency_ms  INT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
