# Operational Runbook — Hermes Adaptive Futures Trading Platform

This document outlines everyday maintenance tasks, monitoring procedures, incident response steps, and deployment procedures.

## Daily Monitoring Tasks

### 1. Health Status Checks
Check health endpoints on all critical services:
```bash
curl http://localhost:8000/health   # Binance Adapter
curl http://localhost:8081/health   # Risk Gateway
curl http://localhost:8082/health   # Model Inference
curl http://localhost:8083/health   # Loss Analyzer
curl http://localhost:8084/health   # Hermes Agent
```

### 2. Grafana Dashboard
Access the dashboard at `http://localhost:3000` (Default Credentials: `admin` / `admin`).
Key metrics to review:
- Local vs. Exchange position mismatches.
- Account equity balance / realized PnL.
- Active strategy version and current market regime.

---

## Deployment Procedures

### 1. Dry Run / Demo Deployment
Deploy in dry-run mode using:
```bash
bash scripts/deploy-demo.sh
```

### 2. Production Deployment
Production requires valid secret API keys and passwords placed under `/run/secrets/`:
```bash
bash scripts/deploy-prod.sh
```

---

## Incident Response & Emergency Procedures

### 1. Emergency Stop (Kill Switch)
If the bot behaves unexpectedly or market volatility triggers risk policy breaches, activate the kill switch via Redis:
```bash
redis-cli -a <REDIS_PASSWORD> set kill_switch:level "red"
```
This forces all new entry intents to be rejected immediately by the Risk Gateway.

### 2. Position Reconciliations
If the local database shows a position mismatch against the exchange, query the reconciler:
```bash
curl http://localhost:8000/reconcile/positions?pair=DOGEUSDT
```
Verify the output, manually close or adjust positions on the Binance UI if required, then restart the adapters to re-initialize balance states.
