#!/usr/bin/env python3
import re

# Read the file
with open('/home/ngodingyuk/deploy/services/market-data-gateway/main.py', 'r') as f:
    content = f.read()

# Find and replace the get_candles function
old_func = '''@app.get("/candles/{pair}/{timeframe}")
async def get_candles(pair: str, timeframe: str, limit: int = 10):
    """
    Endpoint untuk mengambil candle terakhir dari PostgreSQL.
    Freqtrade akan calling ini tiap cycle untuk mendapatkan data terakhir.
    """
    pair = pair.upper()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            pd.read_sql(
                f"SELECT timestamp, open, high, low, close, volume "
                f"FROM market_candles "
                f"WHERE pair = '{pair}' AND timeframe = '{timeframe}' "
                f"ORDER BY timestamp DESC LIMIT {limit}",
                db.bind,
            )
        )
        candles = result.fetchall()
    return [
        {
            "timestamp": c[0],
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        }
        for c in candles
    ]'''

new_func = '''@app.get("/candles/{pair}/{timeframe}")
async def get_candles(pair: str, timeframe: str, limit: int = 10):
    """
    Endpoint untuk mengambil candle terakhir dari PostgreSQL.
    Freqtrade akan calling ini tiap cycle untuk mendapatkan data terakhir.
    """
    pair = pair.upper()
    candles = await get_candles_async(pair, timeframe, limit)
    return candles'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open('/home/ngodingyuk/deploy/services/market-data-gateway/main.py', 'w') as f:
        f.write(content)
    print("✅ Function replaced successfully!")
else:
    print("❌ Old function not found. Let me check what's there...")
    # Show the actual function
    match = re.search(r'@app\.get\("/candles.*?(?=@app\.get|$)', content, re.DOTALL)
    if match:
        print("Found function:")
        print(match.group(0)[:500])
