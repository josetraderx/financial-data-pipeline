-- Optional: CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS ohlcv (
    ts TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    timeframe TEXT NOT NULL DEFAULT '1h',
    PRIMARY KEY (symbol, timeframe, ts)
);

-- If using TimescaleDB, uncomment:
-- SELECT create_hypertable('ohlcv', by_range('ts'), if_not_exists => TRUE);
-- CREATE INDEX IF NOT EXISTS ohlcv_ts_idx ON ohlcv (ts DESC);
-- CREATE INDEX IF NOT EXISTS ohlcv_symbol_tf_idx ON ohlcv (symbol, timeframe);
