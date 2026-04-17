CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS readings (
    device_id UUID NOT NULL,
    control_group INT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    sensor_type TEXT NOT NULL,
    value JSONB NOT NULL
);

-- Create a parent type to managed all the weekly partition tables
SELECT create_hypertable(
    'readings',  -- Table to partiton
    'timestamp', -- Partition
    chunk_time_interval => INTERVAL '1 week'
);