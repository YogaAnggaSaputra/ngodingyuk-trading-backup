#!/bin/bash
# Recreate freqtrade-runtime container dengan image 2026.3 yang baru dibuild.
set -uo pipefail
cd /home/ngodingyuk/deploy

echo "=== 1. Stop bot (graceful) ==="
curl -s -X POST http://localhost:8002/stop -H "Content-Type: application/json" -d '{}' || true
echo ""
sleep 3

echo "=== 2. Recreate container ==="
docker compose up -d --force-recreate --no-deps freqtrade-runtime
echo "compose exit=$?"

echo "=== 3. Tunggu service ready ==="
for i in $(seq 1 30); do
  if curl -sf http://localhost:8002/health > /dev/null 2>&1; then
    echo "ready after ${i}s"
    break
  fi
  sleep 1
done

echo "=== 4. Versi freqtrade di container baru ==="
docker exec deploy-freqtrade-runtime-1 python -c "import freqtrade, ccxt; print('freqtrade', freqtrade.__version__, '| ccxt', ccxt.__version__)"

echo "=== 5. Cek volume user_data (harus kosong, siap restore) ==="
docker exec deploy-freqtrade-runtime-1 sh -c 'find /freqtrade/user_data -maxdepth 2 | head -20'
echo "=== RECREATE DONE ==="
