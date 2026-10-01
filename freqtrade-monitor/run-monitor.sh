#!/bin/bash
# Wrapper untuk menjalankan monitor dengan Discord integration

export PYTHONIOENCODING=utf-8
export PATH="$PATH:/usr/local/bin:/usr/bin"

# Load environment variables
if [ -f /home/ngodingyuk/freqtrade-monitor/.env ]; then
    source /home/ngodingyuk/freqtrade-monitor/.env
fi

cd /home/ngodingyuk/freqtrade-monitor

# Jalankan monitor Python
python3 monitor.py 2> /tmp/freqtrade-monitor-stderr.txt
EXIT_CODE=$?

# Cek dan kirim alert ke Discord jika ada
if [ -f "/tmp/freqtrade-alerts.txt" ] && [ -s "/tmp/freqtrade-alerts.txt" ]; then
    ALERT_CONTENT=$(cat /tmp/freqtrade-alerts.txt)
    
    # Kirim ke Discord
    if [ -n "$DISCORD_WEBHOOK_URL" ] && [ "$DISCORD_WEBHOOK_URL" != "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN" ]; then
        curl -s -X POST "$DISCORD_WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "{\"content\": \"🚨 ALERT FREQTRADE\\n\\n$(echo "$ALERT_CONTENT" | sed 's/"/\\"/g')\"}"
    fi
    
    # Log alert
    echo "[$(date '+%d/%m/%Y %H:%M:%S WIB')] ALERT: $ALERT_CONTENT" >> /home/ngodingyuk/freqtrade-monitor/alerts.log
fi

# Kirim laporan lengkap ke Discord (opsional)
if [ "$SEND_DAILY_REPORT" = "true" ] && [ -f "/tmp/freqtrade-monitor-last.txt" ]; then
    if [ -n "$DISCORD_WEBHOOK_URL" ] && [ "$DISCORD_WEBHOOK_URL" != "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN" ]; then
        REPORT_CONTENT=$(cat /tmp/freqtrade-monitor-last.txt)
        curl -s -X POST "$DISCORD_WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "{\"content\": \"\`\`\`\\n$(echo "$REPORT_CONTENT" | sed 's/"/\\"/g')\\n\`\`\`\"}"
    fi
fi

exit $EXIT_CODE
