#!/usr/bin/env python3
import re

# Read the file
with open('/home/ngodingyuk/deploy/services/market-data-gateway/main.py', 'r') as f:
    content = f.read()

# Replace the _normalize_pair function
old_func = '''def _normalize_pair(symbol: str) -> str:
    """Convert SPOT format (BTCUSDT) to FUTURES format (BTC/USDT:USDT)."""
    symbol = symbol.upper().strip()
    if symbol.endswith("USDT") and "/" not in symbol and ":" not in symbol:
        return symbol.replace("USDT", "/USDT:USDT")
    return symbol'''

new_func = '''def _normalize_pair(symbol: str) -> str:
    """Convert SPOT format (BTCUSDT) to FUTURES format (BTC/USDT:USDT)."""
    symbol = symbol.upper().strip()
    # If already in futures format, return as is
    if "/" in symbol and ":" in symbol:
        return symbol
    # If ends with USDT, convert to futures format
    if symbol.endswith("USDT"):
        return symbol.replace("USDT", "/USDT:USDT")
    # If doesn't end with USDT (e.g., 1000RATS), assume USDT quote
    return symbol + "/USDT:USDT"'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open('/home/ngodingyuk/deploy/services/market-data-gateway/main.py', 'w') as f:
        f.write(content)
    print("✅ Function replaced successfully!")
else:
    print("❌ Old function not found!")
    # Show what's there
    match = re.search(r'def _normalize_pair.*?(?=\n\n|\nclass|\nasync def|\n@app)', content, re.DOTALL)
    if match:
        print("Found:")
        print(match.group(0))
