#!/usr/bin/env python3
"""Update bot config with all available pairs"""
import json
import os

# Read existing config
with open('/tmp/freqtrade_config_88407ff338c44b8ab08ecb02b4639de8.json') as f:
    config = json.load(f)

# Read all available pairs from feather files
pairs = set()
for filename in os.listdir('/freqtrade/user_data/data/futures'):
    if '-5m-futures.feather' in filename and not '_USDT_USDT' in filename:
        pair = filename.replace('-5m-futures.feather', '').replace('_USDT', '')
        pairs.add(pair)

print(f"Found {len(pairs)} pairs from feather files")

# Format pairs for config (USDT format)
pair_list = sorted([f"{p}/USDT:USDT" for p in pairs])
print(f"Total pairs: {len(pair_list)}")

# Update config
config['exchange']['pair_whitelist'] = pair_list[:200]  # Max 200 for now
config['max_open_trades'] = 10
config['stake_amount'] = 100

# Save updated config
with open('/tmp/freqtrade_config_updated.json', 'w') as f:
    json.dump(config, f, indent=2)

print(f"Config saved to /tmp/freqtrade_config_updated.json")
print(f"Pairs in config: {len(config['exchange']['pair_whitelist'])}")
