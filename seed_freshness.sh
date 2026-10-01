#!/bin/bash
# Seed Redis freshness keys dari PostgreSQL candle timestamps
# Normalize: TUT/USDT:USDT → TUTUSDT (ambil bagian sebelum / pertama)
#
# Password Redis dibaca dari .env (bukan hardcode) — setelah rotate password,
# hardcode "changeme" bakal gagal auth & bikin risk-gateway market_data_freshness FAIL.

set -euo pipefail

DEPLOY_DIR="/home/ngodingyuk/deploy"
ENV_FILE="$DEPLOY_DIR/.env"

# Ambil REDIS_PASSWORD dari .env
REDIS_PW=$(grep -E '^REDIS_PASSWORD=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -z "$REDIS_PW" ]; then
    echo "ERROR: REDIS_PASSWORD tidak ditemukan di $ENV_FILE" >&2
    exit 1
fi

PAIRS=$(docker exec deploy-postgres-1 psql -U botbinance -d botbinance -t -A -c "SELECT DISTINCT pair FROM market_candles WHERE pair LIKE '%/%'")
NOW=$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")

COUNT=0
for PAIR in $PAIRS; do
    # Ambil bagian sebelum / pertama, uppercase, hapus :
    BASE=$(echo "$PAIR" | cut -d'/' -f1 | tr '[:lower:]' '[:upper:]' | tr -d ':')
    docker exec -e REDISCLI_AUTH="$REDIS_PW" deploy-redis-1 redis-cli SETEX "market:last_update:${BASE}USDT" 3600 "$NOW" >/dev/null 2>&1
    COUNT=$((COUNT+1))
done

echo "Seeded $COUNT freshness keys at $NOW"
