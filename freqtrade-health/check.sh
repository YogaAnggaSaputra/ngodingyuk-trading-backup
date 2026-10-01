#!/usr/bin/env bash
# Freqtrade health check — cron 5m. Read-only.
set -u
CONTAINER="deploy-freqtrade-runtime-1"
ENV_FILE="/home/ngodingyuk/.hermes/profiles/default/cron/.env"
TMPLOG=/tmp/fthealth_$$.log
trap 'rm -f "$TMPLOG" /tmp/ftstatus_$$*.json' EXIT

NOW=$(date '+%Y-%m-%d %H:%M WIB')

API_HTTP=$(curl -s -o "/tmp/ftstatus_$$.json" -w "%{http_code}" --max-time 10 http://localhost:8002/status 2>/dev/null || echo 000)
API_RUNNING="DOWN"
if [ "$API_HTTP" = "200" ]; then
    API_RUNNING=$(python3 -c "import json; d=json.load(open('/tmp/ftstatus_$$.json')); print('RUNNING' if d.get('running') else 'STUCK')" 2>/dev/null || echo UNKNOWN)
fi

CSTATE=$(docker inspect -f '{{.State.Running}}|{{.RestartCount}}' "$CONTAINER" 2>/dev/null || echo "MISSING|?")
CRUN="${CSTATE%%|*}"; CRESTART="${CSTATE##*|}"

docker logs --since 6m "$CONTAINER" 2>&1 > "$TMPLOG" || true
ERR_COUNT=$(grep -cE -- "Traceback|emergency_exit|Stoploss would trigger immediately" "$TMPLOG"); ERR_COUNT=${ERR_COUNT:-0}
ML_REJ=$(grep -ciE -- "REJECTED: ML service unavailable" "$TMPLOG"); ML_REJ=${ML_REJ:-0}
LOOSE=$(grep -ciE -- "EMERGENCY-LOOSEN-XALERT" "$TMPLOG"); LOOSE=${LOOSE:-0}
LOOSE_LINES=""; [ "$LOOSE" -gt 0 ] && LOOSE_LINES=$(grep -iE -- "EMERGENCY-LOOSEN-XALERT" "$TMPLOG" | tail -3)

OPEN_COUNT=0; OPEN_TRADES=""; SL_MISSING=""
if docker exec "$CONTAINER" test -f /freqtrade/user_data/tradesv3.sqlite 2>/dev/null; then
    OPEN_COUNT=$(docker exec "$CONTAINER" sqlite3 /freqtrade/user_data/tradesv3.sqlite \
        "SELECT COUNT(*) FROM trades WHERE is_open=1;" 2>/dev/null); OPEN_COUNT=${OPEN_COUNT:-0}
    if [ "$OPEN_COUNT" -gt 0 ]; then
        OPEN_TRADES=$(docker exec "$CONTAINER" sqlite3 -separator ' | ' /freqtrade/user_data/tradesv3.sqlite \
            "SELECT pair, CASE is_short WHEN 1 THEN 'SHORT' ELSE 'LONG' END, open_rate, stop_loss, stake_amount FROM trades WHERE is_open=1;" 2>/dev/null)
        SL_MISSING=$(docker exec "$CONTAINER" sqlite3 /freqtrade/user_data/tradesv3.sqlite \
            "SELECT id FROM trades WHERE is_open=1 AND (stop_loss IS NULL OR stop_loss=0);" 2>/null)
        if [ -n "$SL_MISSING" ]; then
            ALERTS="${ALERTS:-}SL MISSING di trade open: #$SL_MISSING\n"
        fi
    fi
fi

RECENT=$(docker exec "$CONTAINER" sqlite3 -separator ' | ' /freqtrade/user_data/tradesv3.sqlite \
    "SELECT pair, CASE is_short WHEN 1 THEN 'SHORT' else 'LONG' END, ROUND(close_profit*100,2), exit_reason, substr(close_date,1,16) FROM trades WHERE is_open=0 ORDER BY id DESC LIMIT 2;" 2>/dev/null)

ALERTS=""
[ "$API_RUNNING" != "RUNNING" ] && ALERTS="Bot tidak RUNNING (HTTP $API_HTTP state=$API_RUNNING)"
[ "$CRUN" != "true" ] && ALERTS="$ALERTS Container NOT running (state=$CRUN)"
[ "$CRESTART" -ge 3 ] 2>/dev/null && ALERTS="$ALERTS Restart count: $CRESTART"
[ "$ERR_COUNT" -gt 0 ] && ALERTS="$ALERTS Fatal errors(6m): $ERR_COUNT"

R="Freqtrade Health — $NOW
─────────────────
Status: $API_RUNNING (HTTP $API_HTTP)
Container: running=$CRUN restarts=$CRESTART
Fatal errors (6m): $ERR_COUNT

Open positions: $OPEN_COUNT"
[ "$OPEN_COUNT" -gt 0 ] && [ -n "$OPEN_TRADES" ] && R="$R
$OPEN_TRADES"

R="$R

Recent closed:"
if [ -n "$RECENT" ]; then
    while IFS=' | ' read -r p d pr ex dt; do
        R="$R
  $p $d ${pr}% ($ex) $dt"
    done <<< "$RECENT"
else
    R="$R
  (none)"
fi

R="$R

ML service: $([ "$ML_REJ" -gt 0 ] && echo "blocked ($ML_REJx fail-closed NORMAL)" || echo OK)"

if [ "$LOOSE" -gt 0 ]; then
    R="$R

EMERGENCY SL LOOSENED — CEK POSISI SEGERA:
$LOOSE_LINES"
fi

if [ -n "${ALERTS:-}" ] && [ "${ALERTS:-}" != " " ]; then
    R="$R

ALERTS:$ALERTS"
else
    R="$R

HEALTHY"
fi

echo "$R"

source "$ENV_FILE" 2>/dev/null
if [ -n "${DISCORD_WEBHOOK_URL:-}" ]; then
    python3 -c "
import json,sys,urllib.request
req = urllib.request.Request(sys.argv[2], data=json.dumps({'content': sys.argv[1]}).encode(), headers={'Content-Type':'application/json'})
try:
    print('Discord:', urllib.request.urlopen(req).status)
except Exception as e:
    print('Discord FAIL:', e)
" "$R" "$DISCORD_WEBHOOK_URL"
fi
