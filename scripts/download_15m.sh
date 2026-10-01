#!/bin/bash
# Download 15m data untuk 100 pair utama (background, estimasi 10-15 menit)
cd /freqtrade

# Ambil daftar pair dari config.backtest.json
PAIRS=$(python3 -c "
import json
with open('/freqtrade/configs/config.backtest.json') as f:
    c = json.load(f)
pairs = c.get('exchange', {}).get('pair_whitelist', c.get('pairs', []))[:100]
print(','.join(pairs))
")

echo "Downloading 100 pairs..."
python3 -m freqtrade download-data \
  --exchange binanceusdm \
  --trading-mode futures \
  --pairs "$PAIRS" \
  --timeframes 15m \
  --timerange 20260701-20260820 \
  --datadir /freqtrade/user_data/data/binanceusdm/futures

echo "DONE"
