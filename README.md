# 8Route — AI Gateway & Unified Model Router 🚀

**8Route** is a lightweight, high-performance OpenAI-compatible AI API proxy and reseller gateway built with FastAPI, SQLite (WAL mode), and an async smart-fallback pipeline engine.

Inspired by **9Router** and **New-API**, 8Route unites dynamic OAuth session token auto-refreshing (e.g. Antigravity Google `ya29...`) with multi-provider upstream routing, token quotas, rate limits, and an interactive admin dashboard.

---

## 🌟 Key Features

1. **Smart Failover & Model Combos**:
   - Define custom pipeline chains (e.g. `swiftlink-coding` $\rightarrow$ Priority 1: Antigravity $\rightarrow$ Priority 2: OpenRouter $\rightarrow$ Priority 3: Mistral/Groq).
   - Instant failover on HTTP 429 / 5xx.

2. **Session / OAuth Auto-Refresh**:
   - Background token refresher for Google OAuth session tokens (`ya29...`).

3. **Reseller & Token Quotas**:
   - Issue keys (`sk-8r-...`) with custom quotas, expiry timestamps, and model permission lists.
   - Real-time token consumption deduction and latency logging.

4. **Web Control Center**:
   - Dark-mode control dashboard with 24h activity chart, real-time log inspector, key management, and built-in interactive Chat Playground.

5. **OpenAI Compatibility**:
   - Standard `/v1/chat/completions` (supporting SSE streaming) and `/v1/models`.

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/PromptLabStudio/8route.git
cd 8route
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 20888 --workers 2
```

### 3. Web Dashboard
Open `http://localhost:20888/` in your browser and use the master key `sk-8r-master-admin-key`.

---

## 📂 Project Structure
```
8route/
├── app/
│   ├── admin.py       # Admin API (Stats, Tokens, Providers, Combos)
│   ├── auth.py        # Token validation & quota deduction
│   ├── db.py          # SQLite WAL initialization & connections
│   ├── main.py        # FastAPI app, routing, streaming responses
│   ├── oauth.py       # Google OAuth token refresher
│   ├── proxy.py       # Upstream request forwarding
│   └── router.py      # Pipeline & virtual model resolver
├── static/
│   └── index.html     # Alpine.js + Tailwind + Chart.js Control Center
├── requirements.txt
└── README.md
```

## 📄 License
MIT License. Created by [PromptLab Studio](https://jemioktavian.my.id).
