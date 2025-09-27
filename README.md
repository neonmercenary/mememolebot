# mememolebot
![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-blue?logo=telegram)
![Solana](https://img.shields.io/badge/Chain-Solana-purple?logo=solana)
![Zero Cost](https://img.shields.io/badge/Cost-$0%20/month-brightgreen)
![Status](https://img.shields.io/badge/Status-Alpha-orange)
[![GitHub stars](https://img.shields.io/github/stars/neonmercenary/mememolebot.svg?style=social)](https://github.com/neonmercenary/mememolebot/stargazers)
[![CI](https://github.com/neonmercenary/mememolebot/actions/workflows/ci.yml/badge.svg)](https://github.com/neonmercenary/mememolebot/actions)

An always-free, lightning-fast Telegram micro-bot that watches the Solana chain for freshly-minted meme coins, scores them in real time, and hands you a ready-to-broadcast Jupiter swap, just one tap to ape. Zero custody, zero code bloat, zero hosting cost: the leanest way to catch the next 100× before it trends.



---

## ⚡ What it does
- Streams new Raydium / Pump.fun pools via Helius gRPC  
- Scores each pool (age, whale buy size, social mentions)  
- Auto-builds a Jupiter swap TX, **partial-signed** by the bot  
- Sends a TG message with a **"Broadcast"** button — you add your signature and fire  
- **Non-custodial**: bot never holds your keys or funds  

---

## 🛠️ Lean-stack (free tier)
| Layer | Tech |
|-------|------|
| Compute | Google Cloud e2-micro (always-free) |
| RPC / gRPC | Helius 1 M req/mo (free) |
| Cache | Redis Labs 30 MB (free) |
| Swap | Jupiter API (free) |
| Language | Python 3.10 |

**Monthly cost = $0** up to ~1 k users.

---

## 🚀 2-minute launch
1. Fork & clone  
```bash
git clone https://github.com/neonmercenary/mememolebot.git && cd mememolebot
```

2. Install (venv recommended)  
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

3. Add secrets to `config.yaml`  
```yaml
telegram_token: "YOUR_BOT_TOKEN"
helius_wss: "wss://mainnet.helius-rpc.com?api-key=YOUR_KEY"
my_keypair: "[170,231,...]"   # bot's key shard (64 bytes)
```

4. Run  
```bash
python bot.py
```

5. Join your own TG channel, wait for 🔥 signal, hit **"Broadcast"** → done.

---

## ⚙️ Config cheat-sheet
| Key | Default | Meaning |
|-----|---------|---------|
| `min_liq_sol` | 30 | ignore pools below 30 SOL liquidity |
| `risk_pct` | 0.5 | % of balance to risk per trade |
| `min_score` | 0.6 | fire signal if heuristic ≥ this |
| `slippage_bps` | 50 | 0.5 % slippage |

---

## 🔐 Security
- **Non-custodial**: bot only holds **one shard** of a 2-of-2 nonce account; you keep the other.  
- Swap instructions **whitelisted** to Jupiter & Raydium only.  
- No performance or return promises — **use at your own risk**.

---

## 📄 License
MIT — do whatever you want (close-source, commercialise, fork); just keep the copyright line.

---

## 🤝 Contribute
PRs welcome: faster heuristics, multi-chain, proper gRPC proto stubs, client-side signer web-app.

---

## ⚠️ Disclaimer
This is experimental software. Meme-coins are extremely volatile; you can lose your entire deposit. The authors are **not responsible** for any financial losses or smart-contract bugs.
```
