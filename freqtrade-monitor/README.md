# Monitor Freqtrade Bot

Script monitoring untuk container `deploy-freqtrade-runtime-1` yang berjalan setiap 5 menit.

## File Struktur

- `monitor.py` - Script utama Python untuk monitoring
- `run-monitor.sh` - Wrapper untuk menjalankan monitor + kirim Discord
- `send-discord.sh` - Helper untuk Discord webhook
- `.env` - Konfigurasi (webhook URL)

## Konfigurasi Discord

Edit file `.env`:
```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
SEND_DAILY_REPORT=true
```

## Cara Menjalankan Manual

```bash
/home/ngodingyuk/freqtrade-monitor/run-monitor.sh
```

## Crontab

Sudah terpasang di crontab: setiap 5 menit
```
*/5 * * * * /home/ngodingyuk/freqtrade-monitor/run-monitor.sh
```

## Output

Laporan akan:
1. Ditampilkan ke stdout (bisa dilihat di log cron)
2. Disimpan ke `/tmp/freqtrade-monitor-last.txt`
3. Dikirim ke Discord jika ada alert (atau setiap run jika `SEND_DAILY_REPORT=true`)

## Yang Dicek

- Status bot (running/tidak)
- Error fatal dalam 6 menit terakhir
- Posisi terbuka dari database
- ML service rejection (normal - fail-closed)
- Emergency SL loosen alerts
- Stoploss terpasang di posisi open
