-- Deletes data older than user defined time to free space
SELECT add_retention_policy('readings', INTERVAL '1 year');