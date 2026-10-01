-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create hypertable for market candles
SELECT create_hypertable('market_candles', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Create hypertable for market snapshots
SELECT create_hypertable('market_snapshots', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Create compression policy (compress data older than 7 days)
SELECT add_compression_policy('market_candles', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_compression_policy('market_snapshots', INTERVAL '7 days', if_not_exists => TRUE);

-- Create retention policy (delete data older than 90 days)
SELECT add_retention_policy('market_candles', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('market_snapshots', INTERVAL '90 days', if_not_exists => TRUE);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_orders_trade_id ON orders(trade_id);
CREATE INDEX IF NOT EXISTS idx_orders_client_order_id ON orders(client_order_id);
CREATE INDEX IF NOT EXISTS idx_fills_order_id ON fills(order_id);
CREATE INDEX IF NOT EXISTS idx_positions_exchange ON positions(exchange_position_id);
CREATE INDEX IF NOT EXISTS idx_trade_dossiers_closed_at ON trade_dossiers(closed_at);
CREATE INDEX IF NOT EXISTS idx_audit_events_type_ts ON audit_events(event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_incidents_severity_status ON incidents(severity, status);

-- Database terpisah untuk Freqtrade internal tables
-- (Freqtrade mengelola schema-nya sendiri; TradeDossier di-sync via webhook)
SELECT 'CREATE DATABASE botbinance_freqtrade OWNER botbinance'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'botbinance_freqtrade')\gexec
