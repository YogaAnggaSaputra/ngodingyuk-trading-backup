#!/bin/bash
# Script untuk mengirim alert ke Discord webhook

REPORT_FILE="/tmp/freqtrade-monitor-last.txt"
ALERT_FILE="/tmp/freqtrade-alerts.txt"

# Cek apakah ada alert
if [ -f "$ALERT_FILE" ] && [ -s "$ALERT_FILE" ]; then
    # Kirim alert ke Discord
    curl -s -X POST "$DISCORD_WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d "{\"content\": \"$(cat "$ALERT_FILE")\"}"
    
    # Hapus file alert setelah dikirim
    rm -f "$ALERT_FILE"
fi

# Kirim laporan normal ke Discord (opsional - bisa dimatikan jika hanya ingin alert)
if [ -f "$REPORT_FILE" ] && [ "$SEND_DAILY_REPORT" = "true" ]; then
    curl -s -X POST "$DISCORD_WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d "{\"content\": \"$(cat "$REPORT_FILE")\"}"
fi
