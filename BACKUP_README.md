# ngodingyuk-trading-backup

Full architecture backup of the ngodingyuk trading system.
VPS: `ngodingyuk.site` — if VPS dies, restore from here.

## What's in this repo

| Path | Contents |
|---|---|
| `docker-compose.yml` | 43-service full stack (main) |
| `services/` | 28 Python services (each: main.py, Dockerfile, requirements.txt) |
| `configs/` | freqtrade configs (live/dry/prod/backtest/demo), grafana, prometheus, alertmanager, risk-gateway |
| `user_data/` | AITradingStrategy.py (active), trade DBs, backtest results |
| `runtime-from-image/` | Baked `config_live.json` (the ACTIVE config), main.py, binance_futures.py |
| `shared/` | quant lib (stochastic, supreme_final) |
| `scripts/` | regime_report, slaudit, backfill, post_exit_regret_worker |
| `alembic/` | DB migrations |
| `docs/` | architecture.md, deployment.md, runbook.md |
| `freqtrade-monitor/` | monitor.py, send-discord.sh, run-monitor.sh |
| `freqtrade-health/` | check.sh |
| `.env.example` | Template — fill in your real values |
| `arsitektur.md` | System architecture doc |

## Services (28)

```
9router, adaptive-whitelist, anomaly-detection, binance-adapter,
capital-allocation, db-migrations, discord-bot, execution-guard,
execution-quality, experiment-orchestrator, freqtrade-runtime,
hermes-agent, loss-analyzer, market-data-gateway, model-inference,
news-alpha, on-chain-engine, orderbook-intelligence,
performance-attribution, position-monitor, post-exit-regret,
predictive-layer, quant-engine, reconciler, risk-gateway,
sentiment-engine, telegram-control, tick-recorder
```

## Active config

`runtime-from-image/runtime/config_live.json` is the config the running
freqtrade-runtime uses (baked into the Docker image, not in `configs/`).
Key params: `max_open_trades=5`, `stake=unlimited 99%`, `isolated margin`,
`dry_run=false`, `BTC/ETH/SOL/... whitelist`.

## How to restore on a fresh VPS

```bash
# 1. Install Docker + docker compose plugin
curl -fsSL https://get.docker.com | sh
sudo apt install docker-compose-plugin -y   # or use the compose v2 bundled

# 2. Clone this repo
cd /opt && git clone https://github.com/YogaAnggaSaputra/ngodingyuk-trading-backup deploy
cd deploy

# 3. Create .env from template — fill in YOUR secrets
cp .env.example .env
# Edit .env: set BINANCE_API_KEY, BINANCE_API_SECRET,
# DB_PASSWORD, DB_ROOT_PASSWORD, REDIS_PASSWORD,
# GRAFANA_ADMIN_PASSWORD, TELEGRAM_BOT_TOKEN, etc.

# 4. Create secrets/ dir (compose references these by path)
mkdir -p secrets
# Write binance_api_key.txt, binance_api_secret.txt,
# discord_bot_token.txt, db_password.txt, grafana_password.txt,
# redis_password.txt  (one value per file, no trailing newline issues)

# 5. Restore user_data (strategy + trade DB)
# The named volume `freqtradeuserdata` in docker-compose maps to
# /freqtrade/user_data. Before first launch, pre-seed the volume:
docker run --rm -v $(pwd)/user_data:/data -v freqtradeuserdata:/dest \
  alpine sh -c 'cp -r /data/. /dest/ 2>/dev/null; true'

# 6. Start everything
docker compose up -d --build

# 7. Verify
docker compose ps
docker logs freqtrade-runtime -f
```

## What is NOT in this repo (excluded by .gitignore)

- `.env` — real credentials (use `.env.example` template)
- `secrets/` — binary credential files
- `user_data/data/` — 345MB feather candle data (re-download with:
  `python download_data.py` or `python download_100.py`)
- `user_data/logs/` — 106MB rotated logs (non-critical)
- `user_data/backtest_results/*.zip` — large backtest archives
- `backup-volumes/` — pgdata tarball (1.2GB DB snapshot)
- `backup-pre-upgrade/` — pre-upgrade data snapshot
