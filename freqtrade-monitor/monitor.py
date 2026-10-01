#!/usr/bin/env python3
import subprocess
import sqlite3
import json
import urllib.request
import sys
from datetime import datetime
import re

def run_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Timeout", 1
    except Exception as e:
        return "", str(e), 1

def check_bot_running():
    """Cek apakah bot Freqtrade masih berjalan"""
    stdout, stderr, rc = run_cmd("curl -s http://localhost:8002/status")
    if rc == 0 and "running" in stdout.lower():
        return True, "Bot berjalan normal"
    elif rc == 0:
        try:
            data = json.loads(stdout)
            if data.get("state") == "running":
                return True, "Bot berjalan normal"
        except:
            pass
    return False, "Bot tidak berjalan atau error"

def count_fatal_errors():
    """Hitung error fatal dalam 6 menit terakhir"""
    cmd = 'docker logs --since 6m deploy-freqtrade-runtime-1 2>&1 | grep -cE -- "Traceback|emergency_exit|Stoploss would trigger immediately"'
    stdout, stderr, rc = run_cmd(cmd)
    try:
        count = int(stdout.strip())
        return count
    except:
        return 0

def get_open_positions():
    """Ambil posisi terbuka dari database SQLite"""
    positions = []
    # Coba cek via DB di container
    cmd = """docker exec deploy-freqtrade-runtime-1 sqlite3 /freqtrade/user_data/tradesv3.sqlite \
             "SELECT pair, amount, open_rate, current_rate, open_profit_pct FROM trades WHERE is_open=1" 2>/dev/null"""
    stdout, stderr, rc = run_cmd(cmd)
    
    if rc == 0 and stdout.strip():
        lines = stdout.strip().split('\n')
        for line in lines:
            parts = line.split('|')
            if len(parts) >= 6:
                positions.append({
                    'pair': parts[0],
                    'amount': float(parts[1]) if parts[1] else 0,
                    'open_rate': float(parts[2]) if parts[2] else 0,
                    'current_rate': float(parts[3]) if parts[3] else 0,
                    'profit_pct': float(parts[4]) if parts[4] else 0
                })
    
    # Fallback: coba curl API
    if not positions:
        cmd = 'curl -s http://localhost:8002/api/v1/trades/open'
        stdout, stderr, rc = run_cmd(cmd)
        if rc == 0:
            try:
                data = json.loads(stdout)
                if isinstance(data, list):
                    for trade in data:
                        positions.append({
                            'pair': trade.get('pair', 'N/A'),
                            'amount': trade.get('amount', 0),
                            'open_rate': trade.get('open_rate', 0),
                            'current_rate': trade.get('open_rate', 0),  # akan diupdate
                            'profit_pct': trade.get('open_profit_pct', 0)
                        })
            except:
                pass
    
    return positions

def check_ml_service():
    """Cek apakah ML service rejection aktif"""
    cmd = 'docker logs --since 6m deploy-freqtrade-runtime-1 2>&1 | grep -iE "REJECTED: ML service unavailable" | tail -2'
    stdout, stderr, rc = run_cmd(cmd)
    if stdout.strip():
        return True, "ML service rejection aktif (normal - fail-closed)"
    return False, None

def check_emergency_alerts():
    """Cek alert emergency loosen"""
    cmd = 'docker logs --since 6m deploy-freqtrade-runtime-1 2>&1 | grep -iE "EMERGENCY-LOOSEN-ALERT" | tail -3'
    stdout, stderr, rc = run_cmd(cmd)
    if stdout.strip():
        return True, stdout.strip()
    return False, None

def check_sl_installed(positions):
    """Verifikasi SL terpasang (simplified check)"""
    # Jika ada posisi open, cek log untuk SL placement
    if not positions:
        return True, "Tidak ada posisi untuk dicek SL-nya"
    
    cmd = 'docker logs --since 6m deploy-freqtrade-runtime-1 2>&1 | grep -iE "setting stoploss"'
    stdout, stderr, rc = run_cmd(cmd)
    if stdout.strip():
        return True, f"SL terpasang untuk {len(positions)} posisi"
    return False, f"WARNING: Posisi open tapi tidak ada log SL placement dalam 6m terakhir"

def main():
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S WIB")
    report_lines = []
    alerts = []
    
    report_lines.append(f"📊 Monitor Freqtrade - {now}")
    report_lines.append("=" * 50)
    
    # 1. Cek bot running
    bot_running, bot_status = check_bot_running()
    report_lines.append(f"✓ Status Bot: {'✅ BERJALAN' if bot_running else '❌ TIDAK BERJALAN'}")
    report_lines.append(f"  {bot_status}")
    
    if not bot_running:
        alerts.append("⚠️ ALERT: Bot tidak berjalan!")
    
    # 2. Hitung error fatal
    error_count = count_fatal_errors()
    report_lines.append(f"✓ Error Fatal (6m): {error_count} kejadian")
    if error_count > 0:
        alerts.append(f"⚠️ ALERT: Ditemukan {error_count} error fatal dalam 6 menit terakhir")
    
    # 3. Posisi terbuka
    positions = get_open_positions()
    report_lines.append(f"✓ Posisi Terbuka: {len(positions)} posisi")
    
    if positions:
        for pos in positions:
            profit = pos.get('profit_pct', 0)
            profit_str = f"+{profit:.2f}%" if profit >= 0 else f"{profit:.2f}%"
            report_lines.append(f"  • {pos['pair']}: {pos['amount']} @ {pos['open_rate']:.4f}, Profit: {profit_str}")
    else:
        report_lines.append("  (Tidak ada posisi terbuka)")
    
    # 4. Cek ML service
    ml_active, ml_status = check_ml_service()
    report_lines.append(f"✓ ML Service: {'Aktif (fail-closed)' if ml_active else 'Tidak ada rejection'}")
    if ml_status:
        report_lines.append(f"  {ml_status}")
    
    # 5. Cek emergency alerts
    emergency_found, emergency_msg = check_emergency_alerts()
    report_lines.append(f"✓ Emergency Alert: {'ADA' if emergency_found else 'Tidak ada'}")
    if emergency_found:
        alerts.append(f"🚨 EMERGENCY: {emergency_msg}")
        report_lines.append(f"  {emergency_msg}")
    
    # 6. Verifikasi SL
    if positions:
        sl_ok, sl_msg = check_sl_installed(positions)
        report_lines.append(f"✓ Status SL: {sl_msg}")
        if not sl_ok:
            alerts.append(f"⚠️ {sl_msg}")
    
    report_lines.append("=" * 50)
    
    # Final verdict
    if not bot_running or error_count > 0 or emergency_found:
        report_lines.append("🔴 STATUS: PERLU PERHATIAN")
    elif positions:
        report_lines.append("🟡 STATUS: Berjalan dengan posisi terbuka")
    else:
        report_lines.append("🟢 STATUS: Sehat (tidak ada posisi, tidak ada error)")
    
    report_text = "\n".join(report_lines)
    
    # Simpan ke file untuk debugging
    with open("/tmp/freqtrade-monitor-last.txt", "w") as f:
        f.write(report_text)
    
    # Cetak ke stdout
    print(report_text)
    
    # Jika ada alert, kirim ke Discord (akan ditangani oleh wrapper)
    if alerts:
        alert_text = "\n".join(alerts)
        with open("/tmp/freqtrade-alerts.txt", "w") as f:
            f.write(alert_text)
        print("\nALERTS_FOUND", file=sys.stderr)
    
    return 0 if not alerts else 1

if __name__ == "__main__":
    sys.exit(main())
