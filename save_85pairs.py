#!/usr/bin/env python3
import json

# Load the latest config from container
import requests

# Config currently has 85 pairs - save it to config.demo.json for persistence
config_path = "/home/ngodingyuk/deploy/services/freqtrade-runtime/configs/freqtrade/config.demo.json"

with open(config_path) as f:
    config = json.load(f)

# Merge with existing 20 pairs config
# Current config.demo.json has 20 pairs, let's update it
pairs_85 = [
    "0G/USDT:USDT", "1000000BOB/USDT:USDT", "1000000MOG/USDT:USDT",
    "1000BONK/USDT:USDT", "1000CAT/USDT:USDT", "1000CHEEMS/USDT:USDT",
    "1000FLOKI/USDT:USDT", "1000LUNC/USDT:USDT", "1000PEPE/USDT:USDT",
    "1000RATS/USDT:USDT", "1000SATS/USDT:USDT", "1000SHIB/USDT:USDT",
    "1000WHY/USDT:USDT", "1000XEC/USDT:USDT", "1000X/USDT:USDT",
    "1INCH/USDT:USDT", "1MBABYDOGE/USDT:USDT", "2Z/USDT:USDT",
    "42/USDT:USDT", "4/USDT:USDT", "A2Z/USDT:USDT", "AAVE/USDT:USDT",
    "ACE/USDT:USDT", "ACH/USDT:USDT", "ACT/USDT:USDT", "ACU/USDT:USDT",
    "ACX/USDT:USDT", "ADA/USDT:USDT", "ADA_USDT/USDT:USDT",
    "AERO/USDT:USDT", "AEVO/USDT:USDT", "AGIX/USDT:USDT", "AGLD/USDT:USDT",
    "AGT/USDT:USDT", "AI16Z/USDT:USDT", "AIGENSYN/USDT:USDT",
    "AIN/USDT:USDT", "AIOT/USDT:USDT", "AIO/USDT:USDT",
    "AIXBT/USDT:USDT", "AI/USDT:USDT", "APE_USDT/USDT:USDT",
    "ATOM_USDT/USDT:USDT", "AVAX_USDT/USDT:USDT", "AXS_USDT/USDT:USDT",
    "BNB_USDT/USDT:USDT", "BTC_USDT/USDT:USDT", "DOGE_USDT/USDT:USDT",
    "DOT_USDT/USDT:USDT", "ETH_USDT/USDT:USDT", "LINK_USDT/USDT:USDT",
    "LTC_USDT/USDT:USDT", "MANA_USDT/USDT:USDT", "PAXG/USDT:USDT",
    "PLAY/USDT:USDT", "PNUT/USDT:USDT", "POL/USDT:USDT", "QTUM/USDT:USDT",
    "RAD/USDT:USDT", "RARE/USDT:USDT", "RAVE/USDT:USDT",
    "RAYSOL/USDT:USDT", "REEF/USDT:USDT", "REI/USDT:USDT",
    "RIF/USDT:USDT", "RLC/USDT:USDT", "RUNE/USDT:USDT", "SAFE/USDT:USDT",
    "SAND_USDT/USDT:USDT", "SANTOS/USDT:USDT", "SEI/USDT:USDT",
    "SKL/USDT:USDT", "SKYAI/USDT:USDT", "SOL_USDT/USDT:USDT",
    "SOPH/USDT:USDT", "SPACE/USDT:USDT", "SPELL/USDT:USDT",
    "SQD/USDT:USDT", "STBL/USDT:USDT", "STO/USDT:USDT", "SUI/USDT:USDT",
    "SUN/USDT:USDT", "TUSDT/USDT:USDT", "TAKE/USDT:USDT",
    "TOSHI/USDT:USDT", "TURTLE/USDT:USDT", "TUT/USDT:USDT",
    "UB/USDT:USDT", "UMA/USDT:USDT", "UNI_USDT/USDT:USDT",
    "USDC/USDT:USDT", "USELESS/USDT:USDT", "USUAL/USDT:USDT",
    "VELVET/USDT:USDT", "VIC/USDT:USDT", "WAVES/USDT:USDT",
    "XAI/USDT:USDT", "XRP_USDT/USDT:USDT", "XVS/USDT:USDT",
    "ZEN/USDT:USDT", "ZKJ/USDT:USDT", "ZRX/USDT:USDT"
]

config['exchange']['pair_whitelist'] = pairs_85
config['max_open_trades'] = 10

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print(f"Updated config.demo.json with {len(pairs_85)} pairs")
