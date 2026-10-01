#!/bin/bash
# Deployment script for demo environment
set -e

echo "🚀 Deploying BotBinance to Demo Environment"

# Check required secrets
if [ ! -f "./secrets/binance_api_key.txt" ]; then
    echo "❌ Missing secrets/binance_api_key.txt"
    exit 1
fi

if [ ! -f "./secrets/binance_api_secret.txt" ]; then
    echo "❌ Missing secrets/binance_api_secret.txt"
    exit 1
fi

if [ ! -f "./secrets/discord_bot_token.txt" ]; then
    echo "❌ Missing secrets/discord_bot_token.txt"
    exit 1
fi

# Pull latest images
echo "📦 Pulling latest images..."
docker compose pull

# Start services
echo "🔧 Starting services..."
docker compose up -d

# Wait for postgres to be ready
echo "⏳ Waiting for PostgreSQL..."
until docker compose exec -T postgres pg_isready -U botbinance -d botbinance > /dev/null 2>&1; do
    sleep 2
done

# Run migrations
echo "🗄️ Running database migrations..."
docker compose exec -T postgres alembic upgrade head

# Health checks
echo "🏥 Running health checks..."
sleep 5

for service in binance-adapter risk-gateway market-data-gateway freqtrade-runtime discord-bot; do
    if curl -sf "http://localhost:8001/health" > /dev/null 2>&1; then
        echo "✅ $service healthy"
    else
        echo "⚠️ $service not responding yet"
    fi
done

echo "✅ Deployment complete!"
echo ""
echo "📊 Grafana: http://localhost:3000"
echo "📈 Prometheus: http://localhost:9090"
echo "🚨 Alertmanager: http://localhost:9093"
echo "🤖 Binance Adapter: http://localhost:8001"
echo "🛡️ Risk Gateway: http://localhost:8003"
echo "📊 Market Data: http://localhost:8004"
echo "⚡ Freqtrade API: http://localhost:8080"
