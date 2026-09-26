-- Runs once when the Postgres volume is first created (docker-entrypoint-initdb.d).
-- Extensions need superuser, so they're created here rather than by the app.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
