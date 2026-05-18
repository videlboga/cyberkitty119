-- Migration: add user_identifiers table to map external provider ids to internal users
-- This file contains SQL compatible with sqlite and postgres (best-effort).

-- Create table (sqlite-compatible)
CREATE TABLE IF NOT EXISTS user_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Unique index to prevent duplicate provider+external_id
CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_external_id ON user_identifiers (provider, external_id);

-- Optional: add foreign key for Postgres if desired (no-op in sqlite)
-- ALTER TABLE user_identifiers ADD CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- Notes:
-- - If you use Alembic, create a proper revision instead of running this raw SQL.
-- - After running, existing users will remain; to migrate existing telegram_id values into
--   user_identifiers you can run an UPDATE script to insert mappings for non-null telegram_id rows.
