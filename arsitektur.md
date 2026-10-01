# Arsitektur Sistem Trading — Hermes Adaptive Futures Trading Platform

> Dokumen ini menjelaskan bagaimana **semua komponen bekerja sebagai satu kesatuan** —
> dari data pasar masuk, keputusan trading, eksekusi order, sampai pembelajaran
> otomatis untuk memperbaiki diri. Bukan daftar service, tapi **alur lengkap
> sebuah trade** dan bagaimana tiap bagian saling melengkapi.

---

## 1. Gambaran Besar (Satu Sistem, Tiga Lapisan)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BINANCE USDT-M FUTURES (Mainnet/Testnet)             │
│                   REST API + WebSocket Market Stream                    │
└───────────────┬──────────────────────────────┬─────────────────────────┘
                │                              │
    ┌───────────▼───────────┐      ┌───────────▼───────────┐
    │  LAPISAN DATA         │      │  LAPISAN EKSEKUSI     │
    │  market-data-gateway  │      │  binance-adapter      │
    │  (candle, ticker,     │      │  (order real, akun,   │
    │   orderbook, likuidasi)│     │   limit-chaser, profiler)
    └───────────┬───────────┘      └───────────┬───────────┘
                │                              │
                ▼                              │
    ┌───────────────────────┐                  │
    │  PostgreSQL (Timescale)│◄─────────────────┤
    │  Redis (bus + state)  │                  │
    └───────────┬───────────┘                  │
                │                              │
    ┌───────────▼───────────┐      ┌───────────▼───────────┐
    │  LAPISAN KEPUTUSAN    │      │  LAPISAN PENGAMAN     │
    │  freqtrade-runtime    │─────►│  risk-gateway         │
    │  (AITradingStrategy)  │      │  (fail-closed)        │
    └───────────┬───────────┘      └───────────┬───────────┘
                │                              │
                │  model-inference (ML)        │
                │  (probabilitas, regime,      │
                │   SL/TP MAE/MFE)             │
                └──────────────┘               │
                                               │
    ┌───────────▼───────────┐      ┌───────────▼───────────┐
    │  LAPISAN PEMBELAJARAN │      │  LAPISAN OBSERVASI    │
    │  loss-analyzer        │      │  prometheus/grafana   │
    │  hermes-agent         │      │  discord-bot          │
    │  experiment-orchestrator│    │  reconciler           │
    └───────────────────────┘      └───────────────────────┘
```

**Tiga lapisan saling bergantung:**
- **Data** memberi makan **Keputusan**
- **Keputusan** melewati **Pengaman** sebelum jadi eksekusi
- **Eksekusi** menghasilkan data baru → **Pembelajaran** → memperbaiki **Keputusan** berikutnya

---

## 2. Alur Satu Trade — Dari Data sampai Order (Loop Eksekusi)

```
1. DATA MASUK
   Binance WS ──► market-data-gateway ──► PostgreSQL (candle 5m/15m/1h/4h/1d)
                                        ──► Redis key market:last_update:DOGEUSDT
                                        ──► Parquet (data lake)

2. SINYAL STRATEGI (tiap candle 5m baru)
   freqtrade-runtime menjalankan AITradingStrategy:
   • Kill zone (jam aktif Asia/London/NY)
   • Confluence score ≥ 70 + ADX ≥ 20 + volume ≥ 1.2x
   • ML confirmation: model-inference /predict (fail-open jika mati)
   • Gate kelayakan: RR ≥ 1.2, SL valid, bukan FOMO/ekstrem

3. UKURAN POSISI (custom_stake_amount)
   • Risk-based sizing, tapi di-floor ke minNotional $5
     (agar order tidak ditolak Binance di micro-account)

4. VALIDASI RISK (WAJIB — fail-closed)
   order ──► risk-gateway /validate:
   • Kill switch aktif? (Redis kill_switch:level)
   • Mode demo/live sesuai policy?
   • Pair ada di allowlist? (DOGE/SOL/1000PEPE/dkk)
   • Market data fresh? (Redis market:last_update)
   • SL valid? Leverage ≤ 5x?
   • Risk aktual (jarak SL × qty) ≤ batas?
   • Exposure (margin = notional ÷ leverage) ≤ 100% equity?
   • Strategi sudah di-deploy? (tabel deployments)
   ── TIDAK LOLOS ──► order DIBATALKAN, tidak pernah ke exchange
   ── LOLOS ──► lanjut

5. EKSEKUSI
   freqtrade ──► binance-adapter /orders (atau /orders/limit utk maker)
   • Validasi minQty + minNotional lokal sebelum kirim
   • Order dicatat di tabel `orders` + publish Redis order:update
   ──► Binance Futures

6. PROTEKSI POSISI
   SL/TP dikirim langsung ke exchange (stoploss_on_exchange)
   agar posisi terbuka SELALU terlindungi walau bot mati.
   SL dinamis: ATR 1.5× (floor 0.5%) atau rekomendasi ML MAE/MFE.
```

---

## 3. Alur Pasca-Trade — Dari Order sampai Perbaikan Diri (Loop Pembelajaran)

```
Trade closed
   │  webhook freqtrade ──► freqtrade-runtime /webhook/trade
   │  • entry: simpan feature_snapshot (dari model-inference) + SL/TP
   │  • exit: update realized_pnl, publish alert:trade_closed
   ▼
TradeDossier (PostgreSQL)  ── satu baris per trade selesai
   │
   ▼
loss-analyzer (tiap 4 jam)
   │  klasifikasi loss: regime_mismatch, poor_timing, sl_noise,
   │  feature_drift, execution_slippage, technical_failure
   │  deteksi pola + buat Incident
   ▼
hermes-agent (tiap 6 jam)
   │  kumpulkan bukti: loss summary, performa per regime, incident
   │  buat Proposal (hanya perubahan yang aman, baca-saja)
   │  publish alert:hermes_proposal
   ▼
experiment-orchestrator (subscribe alert)
   │  auto-accept proposal → buat Experiment
   │  pipeline: backtest → walk-forward → stress → monte-carlo
   │  (jalankan freqtrade backtesting dengan config.backtest.json)
   │  → jika lolos → minta approval Owner
   ▼
Deployment (tabel deployments, status=active)
   │  • auto-seed AITradingStrategy saat startup
   │  • atau manual via POST /deployments
   ▼
risk-gateway check_strategy_approved → order berikutnya diizinkan
   ▼
Strategi versi baru dipakai live ──► siklus berulang
```

**Ini "otak" sistem:** setiap trade menghasilkan data → dianalisis → sistem
belajar → strategi diperbaiki → dideploy → diuji di live. Satu kesatuan utuh.

---

## 4. Model ML — Otak Kedua yang Ikut Ambil Keputusan

```
                    ┌─────────────────────────────┐
                    │      model-inference        │
                    └────────────┬────────────────┘
                                 │
   ┌─────────────┬───────────────┼────────────────┬──────────────────┐
   ▼             ▼               ▼                ▼                  ▼
/features     /predict        /regime        /mae-mfe-predict   /predict/ensemble
(fitur teknikal) (prob & signal) (GMM regime)  (SL/TP optimal)   (stacking: XGB+LGBM+CatBoost)
```

**Dipakai di 3 titik oleh strategi (live/dry-run, fail-open):**
1. **Gate entry** — `/predict`: jika ML bilang SELL kuat, jangan long (dan sebaliknya)
2. **SL dinamis** — `/mae-mfe-predict`: jarak SL optimal dari data historis (floor 0.5%)
3. **TP dinamis** — `/mae-mfe-predict`: exit penuh saat harga sentuh TP rekomendasi ML

**Model dilatih dari data riil (retrainer, tiap 7 hari / manual):**
- GMM regime ← 500+ candle 5m (90 hari)
- MAE/MFE ← 50+ trade closed (180 hari) — feature snapshot dari webhook
- Ensemble ← 50+ trade (label: profit/loss)
- Fallback rule-based jika model belum terlatih → tetap berfungsi

**Fail-open:** jika model-inference mati, strategi TETAP trading dengan aturan
teknikal murni. ML adalah lapisan konfirmasi, bukan single point of failure.

---

## 5. Pengamanan — Berlapis Sebelum Uang Keluar

| Lapisan | Komponen | Cara kerja |
|---------|----------|-----------|
| 1. Strategi | AITradingStrategy | Gate kualitas: kill zone, confluence, RR, FOMO lock |
| 2. Risk Gateway | risk-gateway `/validate` | 9+ cek fail-closed — keraguan = tolak |
| 3. Deployment gate | tabel `deployments` | Order hanya untuk strategi status active |
| 4. Kill switch | Redis `kill_switch:level` | Discord `/kill` atau API — langsung blokir |
| 5. Ukuran order | binance-adapter | minQty + minNotional dicek sebelum kirim |
| 6. SL/TP exchange | stoploss_on_exchange | Posisi terlindungi walau bot mati |
| 7. Circuit breaker | strategi + policy | Daily loss >50% → berhenti |
| 8. Rekonsiliasi | reconciler | Bandingkan lokal vs exchange tiap 30s |

**Kenapa "satu kesatuan"?** Karena pengaman tidak terpisah — strategi yang
menghasilkan order juga yang kena cek, dan cek membaca state dari komponen lain
(Redis dari market-data, deployments dari orchestrator, equity dari adapter).

---

## 6. Komunikasi Antar Komponen (3 Cara)

```
1. DATABASE (sumber kebenaran)
   PostgreSQL + TimescaleDB — semua service baca/tulis tabel yang sama:
   market_candles, trade_dossiers, orders, positions, proposals,
   experiments, deployments, incidents, kill_switch_log

2. REDIS PUB/SUB (event real-time)
   Channel              Publisher                    Subscriber
   alert                freqtrade, loss, hermes,     discord-bot,
                        orchestrator                 orchestrator
   market:data          market-data-gateway          (dicatat, siapa pun bisa)
   order:update         binance-adapter              —
   risk:decision        risk-gateway                 —
   kill:switch          discord-bot                  risk-gateway (via Redis key)
   + Redis state keys: market:last_update:{pair}, kill_switch:level

3. HTTP SERVICE-TO-SERVICE (permintaan langsung)
   freqtrade ──► risk-gateway   /validate  (wajib sebelum order)
   freqtrade ──► binance-adapter /orders   (eksekusi)
   freqtrade ──► model-inference /predict, /mae-mfe-predict
   risk-gateway ─► binance-adapter /account (equity)
   risk-gateway ─► market-data-gateway /orderbook/{pair}
   reconciler ──► binance-adapter /positions, /orders
```

---

## 7. Inventaris Komponen (10 Service + Infra)

| Komponen | Peran dalam kesatuan |
|----------|---------------------|
| **market-data-gateway** | Mata: ambil data pasar, simpan ke DB + Parquet, jaga freshness |
| **binance-adapter** | Tangan: eksekusi order, cek min-qty, account, limit-chaser |
| **freqtrade-runtime** | Otak taktis: jalankan strategi 5m, wire ke semua service |
| **AITradingStrategy** | Keputusan entry/exit: confluence + ML + SL/TP pintar |
| **risk-gateway** | Pengawal: validasi fail-closed sebelum uang keluar |
| **model-inference** | Otak analitis: probabilitas, regime, SL/TP ML, retrain otomatis |
| **loss-analyzer** | Guru: klasifikasi kenapa trade rugi |
| **hermes-agent** | Perencana: usulkan perbaikan strategi berbasis bukti |
| **experiment-orchestrator** | Laboratorium: uji proposal via backtest, kelola deployment |
| **reconciler** | Auditor: cek konsistensi lokal vs exchange |
| **discord-bot** | Komunikasi: notifikasi + kontrol (/kill, /status) |
| **postgres (Timescale)** | Memori: semua data historis, hypertable + kompresi |
| **redis** | Saraf: event bus + state real-time |
| **prometheus/grafana/alertmanager** | Cermin: metrik, dashboard, alert |

---

## 8. Konfigurasi Utama (Satu Sumber Kebenaran)

```
.env                  → TRADE_MODE (demo/live), API keys, MARKET_SYMBOLS
configs/policy.yaml   → policy risk terkunci (pair, leverage 5x, exposure 100%)
configs/freqtrade/*.json → pair_whitelist, timeframe 5m, scalping params
configs/freqtrade/strategies/ → AITradingStrategy.py (logika trading)
docker-compose.yml    → orkestrasi 15 container + limit RAM (total ≤ 8.5GB)
```

**Konsistensi mode (kritis untuk live):**
```
TRADE_MODE=demo  → freqtrade dry_run=true, policy trading_mode=demo (AMAN)
TRADE_MODE=live  → freqtrade dry_run=false, policy trading_mode=live (ORDER REAL)
BINANCE_FUTURES_TESTNET=false → mainnet (live)
```

Semua service membaca env yang sama dari compose — tidak ada konfigurasi ganda.

---

## 9. Ringkasan: Kenapa Ini Satu Kesatuan

1. **Satu database** — semua komponen baca/tulis data yang sama, tidak ada silo
2. **Satu alur wajib** — order TIDAK BISA melewati risk-gateway (fail-closed)
3. **Satu loop belajar** — trade → analisis → proposal → uji → deploy → trade lagi
4. **Satu sumber konfigurasi** — env + policy + strategy, konsisten antar service
5. **Satu bus event** — Redis menghubungkan publisher & subscriber real-time
6. **Fail-safe terhubung** — kill switch dari Discord, freshness dari market-data,
   deployment dari orchestrator — semua saling membaca state

Jika satu bagian mati:
- market-data mati → freshness check gagal → risk-gateway tolak semua (aman)
- model-inference mati → strategi tetap jalan tanpa ML (fail-open)
- discord-bot mati → trading tetap jalan, hanya notifikasi hilang
- risk-gateway mati → order ditolak (fail-closed, tidak ada order tanpa validasi)

**Sistem ini dirancang untuk berhenti dengan aman ketika ada yang salah,
dan belajar memperbaiki diri ketika semuanya benar.**

---

## 10. Cara Membaca Status Kesiapan

```bash
# 1. Semua container up
docker compose ps

# 2. Tidak ada error di log
docker compose logs --tail=50 freqtrade-runtime risk-gateway binance-adapter

# 3. Deployment aktif ada (tanpa ini semua order ditolak)
curl http://localhost:8008/deployments
# → harus ada: {"strategy_version": "AITradingStrategy", "status": "active"}

# 4. Mode sesuai keinginan
# TRADE_MODE=demo → aman | TRADE_MODE=live → order real

# 5. Bot benar-benar berjalan
curl http://localhost:8002/status   # {"running": true}
curl -X POST http://localhost:8002/start   # jika belum running

# 6. Market data mengalir (setelah beberapa menit)
curl http://localhost:8004/candles/DOGEUSDT/5m?limit=5
```
