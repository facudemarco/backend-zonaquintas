-- The legacy free-text opinion list is no longer consumed by the application.
-- This permanently removes the two legacy rows; take a backup first if they
-- need to be retained for archival purposes.
DROP TABLE IF EXISTS users_opinions;
