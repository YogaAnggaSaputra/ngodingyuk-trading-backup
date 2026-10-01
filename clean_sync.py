#!/usr/bin/env python3
"""Clean sync from feather to PostgreSQL with correct format"""
import os
import pyarrow.feather as feather
from datetime import datetime, timezone
import asyncio
import asyncpg

async def sync():
    # Connect to PostgreSQL
    conn = await asyncpg.connect(
        host="postgres",
        database="botbinance",
        user="botbinance",
        password=os.getenv("DB_PASSWORD", "")
    )
    
    # Data directory
    base_dir = '/freqtrade/user_data/data/futures'
    
    # Find all 5m feather files
    files = [f for f in os.listdir(base_dir) if '-5m-futures.feather' in f]
    print(f"Found {len(files)} files")
    
    total = 0
    
    for i, filename in enumerate(files):
        try:
            filepath = os.path.join(base_dir, filename)
            
            # Correct pair format: BTC_USDT_USDT -> BTC/USDT:USDT
            pair = filename.replace('-5m-futures.feather', '').replace('_USDT', '/USDT:USDT')
            
            # Read feather file
            df = feather.read_table(filepath).to_pandas()
            
            if len(df) == 0:
                continue
            
            # Insert using executemany for speed
            rows = []
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for idx, row in df.iterrows():
                rows.append((
                    pair, "5m", idx, 
                    float(row['open']), float(row['high']),
                    float(row['low']), float(row['close']), 
                    float(row['volume']), "binance", now
                ))
            
            if rows:
                await conn.executemany("""
                    INSERT INTO market_candles (pair, timeframe, timestamp, open, high, low, close, volume, source, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (pair, timeframe, timestamp) DO NOTHING
                """, rows)
                total += len(rows)
                print(f"[{i+1}/{len(files)}] {pair}: {len(rows)} candles")
            
        except Exception as e:
            print(f"Error with {filename}: {e}")
    
    # Verify
    result = await conn.fetchval("SELECT COUNT(*) FROM market_candles")
    pairs = await conn.fetchval("SELECT COUNT(DISTINCT pair) FROM market_candles")
    
    print(f"\n{'='*60}")
    print(f"✅ Sync Complete!")
    print(f"📊 Total inserted: {total}")
    print(f"📁 Total records in DB: {result}")
    print(f"📈 Unique pairs: {pairs}")
    
    await conn.close()

asyncio.run(sync())
