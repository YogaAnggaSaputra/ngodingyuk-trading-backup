#!/bin/bash
# Restore OHLCV data + trade DB ke volume freqtradeuserdata setelah upgrade
# ke freqtrade 2026.3. Dijalankan SEKALI setelah container baru up.
set -euo pipefail

BACKUP_DIR=/home/ngodingyuk/deploy/backup-pre-upgrade
CONTAINER=deploy-freqtrade-runtime-1

echo "=== 1. Cek container jalan ==="
docker inspect -f '{{.State.Running}}' "$CONTAINER"

echo "=== 2. Restore OHLCV data (166MB, 136 feather) ==="
docker cp "$BACKUP_DIR/user_data_data/." "$CONTAINER:/freqtrade/user_data/data/"

echo "=== 3. Restore trade DB (6 trades) ==="
docker cp "$BACKUP_DIR/tradesv3.sqlite" "$CONTAINER:/freqtrade/user_data/tradesv3.sqlite"

echo "=== 4. Fix ownership (freqtrade jalan sebagai ftuser) ==="
docker exec -u root "$CONTAINER" chown -R ftuser:ftuser /freqtrade/user_data

echo "=== 5. Verifikasi ==="
docker exec "$CONTAINER" sh -c 'echo "feather: $(find /freqtrade/user_data/data -name "*.feather" | wc -l)"'
docker exec "$CONTAINER" python3 -c "
import sqlite3
c = sqlite3.connect('/freqtrade/user_data/tradesv3.sqlite').cursor()
c.execute('SELECT COUNT(*) FROM trades')
print('trades:', c.fetchone()[0])
"
echo "=== RESTORE DONE ==="
