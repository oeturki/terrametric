CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS readings (
    device_id UUID NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    key TEXT NOT NULL,
    double DOUBLE PRECISION,
    string TEXT,
    bool BOOLEAN,
    bignum BIGINT
);