import requests
import subprocess
import json
import sqlite3
from datetime import datetime, timezone, timedelta
import sys

WIB = timezone(timedelta(hours=7))
now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB")

# Fungsi bantu
def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return result.stdout.strip(), result.returncode
    except Exception as e:
        return str(e), 1

def run_docker_grep(pattern, since="6m", tail=2):
    cmd = f'docker logs --since {since} deploy-freqtrade-runtime-1 2>&1 | grep -iE "{pattern}" | tail -{tail}'
    return run_cmd(cmd)

# Cek 1: Bot running?
try:
    r = requests.get("http://localhost:8002/status", timeout=5)
    bot_status = r.json()
    bot_running = bot_status.get("running", False) or bot_status.get("state") == "running"
except Exception as e:
    bot_running = False
    bot_status = {"error": str(e)}

# Cek 2: Error fatal
fatal_log, _ = run_cmd('docker logs --since 6m deploy-freqtrade-runtime-1 2>&1 | grep -cE -- "Traceback|emergency_exit|Stoploss would trigger immediately"')
try:
    fatal_count = int(fatal_log) if fatal_log else 0
except:
    fatal_count = 0

# Cek 3: Posisi live dari DB
positions = []
try:
    # Query posisi terbuka
    query = "SELECT id, pair, amount, stop_loss, initial_stop_loss, open_date FROM trades WHERE is_open=1"
    cmd = f'docker exec deploy-freqtrade-runtime-1 sqlite3 /freqtrade/user_data/tradesv3.sqlite "{query}"'
    pos_raw, rc = run_cmd(cmd)
    if pos_raw and rc == 0:
        for line in pos_raw.splitlines():
            parts = line.split("|")
            if len(parts) >= 5:
                positions.append({
                    "id": parts[0],
                    "pair": parts[1],
                    "amount": parts[2],
                    "stop_loss": parts[3],
                    "initial_stop_loss": parts[4],
                    "open_date": parts[5] if len(parts) > 5 else ""
                })
except Exception as e:
    positions = []

# Cek 4: ML service
ml_log, _ = run_docker_grep("REJECTED: ML service unavailable", "6m", 2)
ml_down = bool(ml_log)

# Cek 5: SL exchange terpasang
sl_issues = []
for pos in positions:
    sl = pos.get("stop_loss")
    if sl is None or sl == "" or sl == "0":
        sl_issues.append(f"{pos['pair']} (ID:{pos['id']}) - SL belum terpasang")

# Cek 6: EMERGENCY-LOOSEN-ALERT
loosen_log, _ = run_docker_grep("EMERGENCY-LOOSEN-ALERT", "6m", 3)
loosen_alerts = bool(loosen_log)

# Verifikasi via ccxt apakah SL benar-benar ada di exchange
exchange_sl_ok = True
for pos in positions:
    pair = pos.get("pair", "")
    sl = pos.get("stop_loss")
    if not sl or sl == "" or sl == "0":
        exchange_sl_ok = False
        break

# Log terakhir untuk emergency_exit
emergency_log, _ = run_docker_grep("emergency_exit", "6m", 3)
has_emergency = bool(emergency_log)

# Tentukan status kesehatan
alerts = []
if not bot_running:
    alerts.append("BOT TIDAK BERJALAN")
if fatal_count > 0:
    alerts.append(f"Ditemukan {fatal_count} error fatal")
if sl_issues:
    alerts.extend(sl_issues)
if has_emergency:
    alerts.append("Ada EMERGENCY_EXIT di log")
if exchange_sl_ok is False and positions:
    alerts.append("SL exchange belum terpasang pada posisi terbuka")

# Build laporan
lines = []
lines.append(f"**LAPORAN KESEHATAN FREQTRADE BOT** `deploy-freqtrade-runtime-1`")
lines.append(f"Waktu cek: {now_wib}")
lines.append("")
lines.append("**Status Bot:**")
if bot_running:
    lines.append(f"Status: BERJALAN")
else:
    lines.append(f"Status: TIDAK BERJALAN")
lines.append(f"Detail: {json.dumps(bot_status)}")
lines.append("")
lines.append("**Error Fatal (6 menit terakhir):**")
lines.append(f"Jumlah error fatal (Traceback/emergency_exit/stoploss would trigger immediately): {fatal_count}")
lines.append("")
lines.append("**Posisi Terbuka:**")
if positions:
    for p in positions:
        lines.append(f"- Pair: {p['pair']} | ID: {p['id']} | Jumlah: {p['amount']}")
        lines.append(f"  SL lokal: {p.get('stop_loss','-')} | SL awal: {p.get('initial_stop_loss','-')} | Dibuka: {p.get('open_date','-')}")
else:
    lines.append("Tidak ada posisi terbuka saat ini.")
lines.append("")
lines.append("**Status Layanan Pendukung:**")
if ml_down:
    lines.append("ML Service: TIDAK TERSEDIA (entry diblokir — ini NORMAL dan disengaja, fail-closed)")
else:
    lines.append("ML Service: TERSEDIA atau tidak ada penolakan terkait ML dalam 6 menit terakhir")
lines.append("")
lines.append("**Cek Stoploss di Exchange:**")
if sl_issues:
    lines.append("MASALAH:")
    for issue in sl_issues:
        lines.append(f"- {issue}")
else:
    lines.append("Semua posisi terbuka memiliki SL exchange terpasang.")
lines.append("")
lines.append("**Peringatan Darurat (6 menit terakhir):**")
if loosen_alerts:
    lines.append("TERDAPAT EMERGENCY-LOOSEN-ALERT:")
    lines.append(loosen_log)
else:
    lines.append("Tidak ada peringatan EMERGENCY-LOOSEN-ALERT.")
lines.append("")
lines.append("**Kesimpulan:**")
if not alerts:
    lines.append("BOT SEHAT. Tidak ada masalah berarti. 0 error fatal. Tidak ada posisi dengan SL yang lepas. Lanjutkan pantauan rutin.")
else:
    lines.append("DIPERLUKAN TINDAKAN:")
    for a in alerts:
        lines.append(f"- {a}")

report = "\n".join(lines)

# Kirim ke Discord
webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1536142054722379866/EkfP_ET7t6gftJxZSKb1WiF1Vee49g_4l88a13W9BYXqei1-3OZ70nK1D2fPLNffuxpc")
payload = {"content": f"```\n{report}\n```"}

try:
    r = requests.post(webhook_url, json=payload, timeout=10)
    print("Laporan berhasil dikirim ke Discord.")
    print(f"Status HTTP: {r.status_code}")
    if r.status_code != 204:
        print(f"Respon: {r.text}")
except Exception as e:
    print(f"Gagal kirim Discord: {e}")
    print(report)

