# BotBinance Deployment Guide

## Prerequisites

- Docker 24+
- Docker Compose 2+
- VPS with 8+ vCPU, 32GB RAM, 500GB NVMe
- Domain with Cloudflare (optional)
- Binance Futures API credentials (mainnet; testnet via `BINANCE_FUTURES_TESTNET=true`)
- Discord Bot Token & Channel ID

## Quick Start (Development)

```bash
# 1. Clone and setup
cd botbinance
cp .env.example .env
# Edit .env with your values

# 2. Create secrets
mkdir -p secrets
echo "YOUR_API_KEY" > secrets/binance_api_key.txt
echo "YOUR_API_SECRET" > secrets/binance_api_secret.txt
echo "YOUR_DISCORD_BOT_TOKEN" > secrets/discord_bot_token.txt

# 3. Start stack
docker compose up -d

# 4. Run migrations
docker compose exec postgres alembic upgrade head

# 5. Verify
curl http://localhost:8001/health
curl http://localhost:3000 (Grafana: admin / $GRAFANA_ADMIN_PASSWORD)
```

## Production Deployment

### Server Setup

```bash
# On VPS
mkdir -p /opt/botbinance
cd /opt/botbinance

# Clone repo
git clone <your-repo> .
git checkout main

# Setup Docker secrets (Swarm mode) or use .env
docker swarm init
echo "prod_key" | docker secret create binance_api_key -
echo "prod_secret" | docker secret create binance_api_secret -
echo "prod_token" | docker secret create discord_bot_token -
echo "db_pass" | docker secret create db_password -
echo "grafana_pass" | docker secret create grafana_admin_password -

# Deploy
docker stack deploy -c docker-compose.yml -c docker-compose.prod.yml botbinance
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `BINANCE_API_KEY` | Binance Futures API Key | Yes |
| `BINANCE_API_SECRET` | Binance Futures API Secret | Yes |
| `BINANCE_FUTURES_TESTNET` | `true` for testnet, `false` for mainnet | No |
| `BINANCE_FUTURES_BASE_URL` | Defaults to `https://fapi.binance.com` (mainnet) | No |
| `BINANCE_FUTURES_LEVERAGE` | Default leverage per symbol (default `3`) | No |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | No (superseded by Discord) |
| `DISCORD_BOT_TOKEN` | Discord bot token | Yes |
| `DISCORD_CHANNEL_ID` | Discord channel for alerts & commands | Yes |
| `DISCORD_AUTHORIZED_USER_ID` | Discord user ID allowed to run commands | Yes |
| `DB_PASSWORD` | PostgreSQL password | Yes |
| `REDIS_PASSWORD` | Redis password | Yes |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password | Yes |

### Binance Futures API Setup

1. **Testnet (optional, safe)**: https://testnet.binancefuture.com
   - Create a testnet API key (demo funds, no real money)
   - Set `BINANCE_FUTURES_TESTNET=true`

2. **Mainnet (live)**:
   - Create API key at https://www.binance.com/en/my/settings/api-management
   - Enable **Enable Futures** permission only (Read + Trade, no Withdraw)
   - IP-whitelist your VPS
   - Keep `BINANCE_FUTURES_TESTNET=false`
   - No passphrase needed (unlike Bitget)

### Monitoring Access

- **Grafana**: `http://your-vps:3000` (admin / $GRAFANA_ADMIN_PASSWORD)
- **Prometheus**: `http://your-vps:9090`
- **Alertmanager**: `http://your-vps:9093`

### Discord Commands

```
/status      - Full system status
/positions   - Open positions
/equity      - PnL summary
/kill yellow - Set kill switch YELLOW
/kill orange - Set kill switch ORANGE
/kill red    - Set kill switch RED
/kill black  - Set kill switch BLACK
/resume      - Resume trading (GREEN)
/logs 20     - Last 20 incidents
```

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Discord   │     │   Grafana    │     │  Prometheus  │
│    Bot      │     │  Dashboards  │     │   Metrics    │
└──────┬──────┘     └──────┬───────┘     └──────┬───────┘
       │                   │                    │
       ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network                            │
│  ┌───────────┐ ┌────────────┐ ┌──────────┐ ┌────────────┐  │
│  │ Binance   │ │ Risk       │ │ Market   │ │ Freqtrade  │  │
│  │ Adapter   │ │ Gateway    │ │ Data GW  │ │ Runtime    │  │
│  │ :8001     │ │ :8003      │ │ :8004    │ │ :8080      │  │
│  └─────┬─────┘ └─────┬──────┘ └────┬─────┘ └─────┬──────┘  │
│        │             │             │             │          │
│        └─────────────┼─────────────┼─────────────┘          │
│                      ▼             ▼                        │
│              ┌──────────────┐ ┌───────────┐                │
│              │ PostgreSQL   │ │ Redis     │                │
│              │ (Timescale)  │ │ (Cache/   │                │
│              │ :5432        │ │  PubSub)  │                │
│              └──────────────┘ └───────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## Service Ports

| Service | Internal | External | Description |
|---------|----------|----------|-------------|
| Binance Adapter | 8000 | 8001 | Exchange API |
| Risk Gateway | 8000 | 8003 | Pre-trade checks |
| Market Data GW | 8000 | 8004 | Candles, tickers |
| Freqtrade Runtime | 8080 | 8080 | Trading engine |
| Discord Bot | - | - | Alerts & control |
| Reconciler | - | - | State sync |
| PostgreSQL | 5432 | 5432 | TimescaleDB |
| Redis | 6379 | 6379 | Cache & PubSub |
| Prometheus | 9090 | 9090 | Metrics |
| Grafana | 3000 | 3000 | Dashboards |
| Alertmanager | 9093 | 9093 | Alert routing |

## Database Migrations

```bash
# Create new migration
docker compose exec postgres alembic revision --autogenerate -m "description"

# Apply migrations
docker compose exec postgres alembic upgrade head

# Rollback
docker compose exec postgres alembic downgrade -1
```

## Backup & Recovery

```bash
# Backup database
docker compose exec -T postgres pg_dump -U botbinance botbinance > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20260730.sql | docker compose exec -T postgres psql -U botbinance botbinance

# Automated (cron)
0 2 * * * docker exec botbinance-postgres pg_dump -U botbinance botbinance | gzip > /backups/botbinance_$(date +\%Y\%m\%d).sql.gz
```

## Troubleshooting

### Bot not trading
```bash
# Check kill switch
curl http://localhost:8003/checks | jq

# Check risk gateway logs
docker compose logs risk-gateway

# Check freqtrade
curl http://localhost:8080/api/v1/status
```

### WebSocket disconnected
```bash
# Check market data gateway
docker compose logs market-data-gateway

# Restart
docker compose restart market-data-gateway binance-adapter
```

### Position mismatch
```bash
# Force reconciliation
curl -X POST http://localhost:8001/reconcile/positions?pair=DOGEUSDT

# Check incidents
curl http://localhost:8003/checks | jq '.checks[] | select(.name=="reconciliation")'
```

### High API errors
```bash
# Check Binance adapter
docker compose logs binance-adapter | grep -i error

# Check rate limits
curl http://localhost:8001/metrics | grep rate_limit
```

## Scaling

### Horizontal (Future)
- Add more Binance Adapters behind load balancer
- Separate services to different hosts
- Use Kubernetes for orchestration

### Vertical (Current)
- Increase container resources in `docker-compose.yml`
- PostgreSQL: `shared_buffers = 25% RAM`, `effective_cache_size = 75% RAM`
- Redis: `maxmemory 2gb`, `maxmemory-policy allkeys-lru`

## Security Checklist

- [ ] All secrets in Docker Secrets (not .env)
- [ ] API keys: Trade only, no Withdraw
- [ ] Binance API key IP-whitelisted to VPS
- [ ] VPS firewall: Only 22, 80, 443, 3000, 9090 from your IP
- [ ] PostgreSQL: SSL required, password auth
- [ ] Redis: Password required, bind to docker network only
- [ ] Grafana: Admin password changed, no anonymous access
- [ ] Discord: Authorized user ID restricted, commands whitelisted
- [ ] Regular: `docker image prune`, security updates

## Runbooks

See `docs/runbooks/` for detailed procedures:
- `deploy.md` - Deployment steps
- `rollback.md` - Rollback procedure
- `kill-switch.md` - Kill switch operation
- `reconcile.md` - Manual reconciliation
- `add-pair.md` - Adding new trading pairs
- `incident-response.md` - Incident handling

## Phase 1 Definition of Done

- [ ] `docker compose up -d` → all services healthy < 2 min
- [ ] Bot restart 10x → 0 duplicate orders
- [ ] Position sync verified after restart
- [ ] SL/TP verified active after entry
- [ ] Kill switch blocks entry < 2s
- [ ] All secrets in Docker Secrets
- [ ] Grafana: equity, PnL, DD, exposure, SL/TP status, WS health
- [ ] CI/CD: PR → build → test → deploy-demo (manual approve)
- [ ] Runbooks tested and documented
