-- Squash data to free space after user defined time period
ALTER TABLE readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'control_group, device_id, key',
    timescaledb.compress_orderby   = 'timestamp DESC'
);

-- Set compression policy default 30 days
SELECT add_compression_policy('readings', INTERVAL '30 days');