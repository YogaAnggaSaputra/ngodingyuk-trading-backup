#!/bin/bash
# Restart bot freqtrade dengan config baru (db_url + logfile di volume).
set -uo pipefail

echo "=== 1. Stop bot ==="
curl -s -X POST http://localhost:8002/stop -H "Content-Type: application/json" -d '{}' || true
echo ""
sleep 3

echo "=== 2. Restart container (reload main.py) ==="
docker restart deploy-freqtrade-runtime-1
for i in $(seq 1 30); do
  curl -sf http://localhost:8002/health > /dev/null 2>&1 && { echo "ready after ${i}s"; break; }
  sleep 1
done

echo "=== 3. Start bot ==="
curl -s -X POST http://localhost:8002/start -H "Content-Type: application/json" -d '{}'
echo ""

echo "=== 4. Tunggu freqtrade boot (60s) ==="
sleep 60

echo "=== 5. Config aktif ==="
docker exec deploy-freqtrade-runtime-1 python3 -c "
import json, glob
f = sorted(glob.glob('/tmp/freqtrade_config_*.json'))[-1]
c = json.load(open(f))
for k in ['db_url','logfile','max_open_trades','stake_amount','dry_run','trading_mode','margin_mode']:
    print(f'  {k}: {c.get(k)}')
"

echo "=== 6. Log freqtrade (filtered) ==="
docker exec deploy-freqtrade-runtime-1 sh -c \
  "grep -viE 'PerformanceWarning|FutureWarning|frame.insert|pd.concat|newframe|incompatible dtype' /freqtrade/user_data/logs/freqtrade.log 2>/dev/null | tail -30"

echo "=== 7. Status + trades ==="
curl -s http://localhost:8002/status; echo ""
docker exec deploy-freqtrade-runtime-1 python3 -c "
import sqlite3
c = sqlite3.connect('/freqtrade/user_data/tradesv3.sqlite').cursor()
c.execute('SELECT COUNT(*), SUM(is_open) FROM trades')
n, o = c.fetchone()
print(f'  trades: {n} total, {o or 0} open')
"
echo "=== DONE ==="
