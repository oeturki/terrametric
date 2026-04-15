CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS readings (
    control_group INT NOT NULL,
    device_id UUID NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    key TEXT NOT NULL,
    double DOUBLE PRECISION,
    string TEXT,
    bool BOOLEAN,
    bignum BIGINT
);

-- Create a parent type to managed all the weekly partition tables
SELECT create_hypertable(
    'readings',  -- Table to partiton
    'timestamp', -- Partition
    chunk_time_interval => INTERVAL '1 week'
);