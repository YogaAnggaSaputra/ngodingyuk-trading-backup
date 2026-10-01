#!/bin/bash
# Freqtrade health monitor cron (5-min). Bahasa Indonesia.
STATE=/home/ngodingyuk/.freqtrade_monitor_state
LOG=/home/ngodingyuk/freqtrade_monitor.log
STAMP="$(date '+%d/%m %H:%M') WIB"

lcount() { docker logs --since 6m deploy-freqtrade-runtime-1 2>&1 | grep -cE -- "$1" || true; }

# cursor: skip log lines already counted in previous run
cursor=$(( $(docker logs --since 6m deploy-freqtrade-runtime-1 2>&1 | wc -l) - ${2:-0} ))
ERR=$(( $(lcount "Traceback|emergency_exit|Stoploss would trigger immediately") - $cursor ))
[ "$ERR" -lt 0 ] && ERR=0

http=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/status)
err2=$(( $(lcount "-2021") - $cursor )); [ "$err2" -lt 0 ] && err2=0

trades=$(docker exec deploy-freqtrade-runtime-1 sh -c 'sqlite3 /freqtrade/user_data/tradesv3.sqlite "SELECT pair, CASE WHEN is_short=1 THEN '\''short'\'' ELSE '\''long'\'' END, ROUND(open_rate,6), COALESCE(ROUND(realized_profit,4),0), ROUND(open_trade_value,2), ROUND(amount,6), ROUND(COALESCE(stop_loss_pct,0),4), COALESCE(ROUND(liquidation_price,6),0) FROM trades WHERE is_open=1 ORDER BY open_date DESC"' 2>/dev/null || true)

lines=0; stderr=''
while IFS= read -r ln; do
  # fallback PnL when sqlite has none: use REST
  set -- $ln; pair=$1; side=$2; rate=$3; pnl=$4; ovals=$5; amt=$6; slp=$7; liq=$8
  [ "$pair" = "$p" ] && continue
  p=$pair
  if [ "$pnl" = "0" ] && [ "$slp" = "0" ]; then
    q=$(curl -s "https://fapi.binance.com/fapi/v1/ticker/price?symbol=${pair//\//}" | grep -oE '"price":"[0-9.]+' | head -1 | cut -d'"' -f4)
    pnl=$(awk -v c="$q" -v r="$rate" -v v="$ovals" -v d="$amt" -v s="$side" 'BEGIN{if(c==""||c==0){print "-";exit} p=(c-r)*d; if(s=="short")p=-p; printf "%.4f",p/v*100}')
  fi
  lines=$((lines+1))
  printf "   - %s %s | rate %s | pnl %s%% | nilai %s %s | SL %.2f%%%s\n" "$pair" "$side" "$rate" "$pnl" "$ovals" "$amt" "$slp" "$([ "$liq" != "0" ] && echo " | liq $liq")" >> "$LOG"
done <<< "$trades"
stderr=$(printf '%s\n' "$trades" | grep -i error | head -1)
[ -n "$stderr" ] && [ -n "$2" ] && echo "   - (posisi terbuka hanya saat REST PnL dimuat; error sqlite: $stderr)" >> "$LOG"

OPEN=$(docker exec deploy-freqtrade-runtime-1 sh -c 'sqlite3 /freqtrade/user_data/tradesv3.sqlite "SELECT COUNT(*) FROM trades WHERE is_open=1"' 2>/dev/null | tr -d '[:space:]')
[ "$OPEN" = "0" ] && OPEN=0
ALERT=$(grep -ciE "EMERGENCY-LOOSEN-ALERT" <<< "$(docker logs --since 6m deploy-freqtrade-runtime-1 2>&1 | tail -200)" || true)

{
  printf -- "----------------------------------------\n"
  if [ "$http" = "200" ]; then echo "STATUS: running  [OK]"; else echo "STATUS: $http  [!!! PERHATIKAN]"; fi
  printf 'ERROR_FATAL: %s\n' "$ERR"
  printf 'ERROR_(-2021): %s\n' "$err2"
  printf 'POSISI_TERBUKA: %s\n' "$OPEN"
  if [ "$OPEN" -gt 0 ]; then
    printf 'SL_EXCHANGE_TERPASANG: %s\n' "$(docker exec deploy-freqtrade-runtime-1 sh -c "python -c 'import ccxt,json;e=ccxt.binance({\"options\":{\"defaultType\":\"future\"}});o=[x for x in e.fetch_positions() if float(x.get(\"contracts\") or 0)!=0];print(json.dumps([{ \"pair\":p[\"symbol\"], \"side\":p[\"side\"], \"pnl\":round(p.get(\"unrealizedPnl\") or 0,4), \"sl\":p.get(\"stopLossPrice\"), \"tp\":p.get(\"takeProfitPrice\")} for p in o]))' 2>/dev/null || echo 'GAGAL')" 2>/dev/null || true)"
  fi
  if [ "$ALERT" -gt 0 ]; then
    printf 'ALERT_SL_LONGGAR: %s\n' "$ALERT"
    echo "   * Posisi dengan SL dilonggarkan (risk > cap, efek gap/restart). SARAN: cek posisi." 
  fi
  echo "--- $(date '+%Y-%m-%d %H:%M:%S') WIB ---"
} >> "$LOG"

tail -12 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
echo "$STAMP lines=$lines error=$ERR http=$http" > "$STATE"
