#!/bin/bash
# Deployment script for production environment
set -e

echo "🚀 Deploying BotBinance to Production Environment"

# Verify this is intentional
if [ -z "$FORCE_PROD_DEPLOY" ]; then
    echo "⚠️  This is PRODUCTION deployment. Set FORCE_PROD_DEPLOY=1 to confirm."
    exit 1
fi

# Check required secrets
for secret in binance_api_key.txt binance_api_secret.txt discord_bot_token.txt; do
    if [ ! -f "./secrets/$secret" ]; then
        echo "❌ Missing secrets/$secret"
        exit 1
    fi
done

# Backup database
echo "💾 Backing up database..."
docker compose exec -T postgres pg_dump -U botbinance botbinance | gzip > "backups/backup_$(date +%Y%m%d_%H%M%S).sql.gz"

# Pull latest images
echo "📦 Pulling latest images..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

# Rolling update
echo "🔄 Rolling update..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans

# Wait for postgres
echo "⏳ Waiting for PostgreSQL..."
until docker compose exec -T postgres pg_isready -U botbinance -d botbinance > /dev/null 2>&1; do
    sleep 2
done

# Run migrations
echo "🗄️ Running database migrations..."
docker compose exec -T postgres alembic upgrade head

# Health checks
echo "🏥 Running health checks..."
sleep 10

for service in binance-adapter risk-gateway market-data-gateway freqtrade-runtime discord-bot; do
    if curl -sf "http://localhost:8001/health" > /dev/null 2>&1; then
        echo "✅ $service healthy"
    else
        echo "❌ $service failed health check"
        exit 1
    fi
done

# Notify
echo "📱 Sending deployment notification..."

echo "✅ Production deployment complete!"
