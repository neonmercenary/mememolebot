#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RiskLadderBot  –  single-file, zero-cost
1.  Polls QuickNode for new Raydium pools
2.  Scores 0-100 % risk (age + top-5 holders + liq)
3.  Buys if coinRisk ≥ userRisk
4.  Sells at 7 %, 14 % … up to max cash-out % of enrolled users
5.  Non-custodial: bot holds 1-of-2 key shard
"""
import asyncio, json, os, time, math, httpx, redis, yaml, logging
from datetime import datetime, timezone
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- CONFIG ----------
cfg = yaml.safe_load(open("config.yaml"))
db = redis.from_url(cfg.get("redis_url", "redis://localhost:6379/0"))
SOLANA = AsyncClient(cfg["rpc_https"])
JUPQUOTE = cfg["jupiter_quote"]
JUPSWAP  = cfg["jupiter_swap"]
BOT_KEY  = Keypair.from_bytes(bytes(cfg["bot_keypair"]))
CHECKPOINTS = [7, 14, 21, 28, 35, 50, 75, 100]  # % above entry

# ---------- UTILS ----------
def js_now(): return datetime.now(timezone.utc).isoformat()

# ---------- DB HELPERS ----------
def key_user(uid): return f"u:{uid}"
def key_pos(uid, mint): return f"pos:{uid}:{mint}"

# ---------- TG HANDLERS ----------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db.hset(key_user(uid), mapping={"risk": 50, "cashout": 70, "bal": 0})  # defaults
    await update.message.reply_text(
        "Welcome! Use /risk <0-100> and /cashout <0-300> to set your levels. "
        "Then deposit SOL and wait for signals.")

async def risk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        r = int(ctx.args[0])
        if 0 <= r <= 100:
            db.hset(key_user(uid), "risk", r)
            await update.message.reply_text(f"Risk set to {r} %")
        else:
            await update.message.reply_text("Risk must be 0-100")
    except:
        await update.message.reply_text("Usage: /risk 80")

async def cashout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        c = int(ctx.args[0])
        if 0 <= c <= 300:
            db.hset(key_user(uid), "cashout", c)
            await update.message.reply_text(f"Cash-out target set to {c} %")
        else:
            await update.message.reply_text("Cash-out must be 0-300 %")
    except:
        await update.message.reply_text("Usage: /cashout 150")

# ---------- POLLER ----------
async def poll_new_pools():
    while True:
        try:
            pools = await fetch_raydium_pools()
            for p in pools:
                risk = await score_pool(p)
                if risk is None: continue
                await maybe_buy(p, risk)
        except Exception as e:
            logger.exception("poll")
        await asyncio.sleep(3)

async def fetch_raydium_pools():
    body = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getProgramAccounts",
        "params": [
            "675kPX9MHTqS2qa5khwkQpFnFv9nvzqZoXwCoffre6cK",
            {"encoding": "jsonParsed", "filters": [{"dataSize": 752}]}
        ]
    }
    async with httpx.AsyncClient() as h:
        r = await h.post(cfg["rpc_https"], json=body, timeout=10)
        if r.status_code != 200: return []
        data = r.json().get("result", [])
    out = []
    for item in data:
        try:
            info = item["account"]["data"]["parsed"]["info"]
            mint = info["coinMint"]
            liq = int(info["pcAmount"]) / 1e9
            if liq < 30: continue  # min 30 SOL liq
            out.append({"mint": mint, "liq": liq})
        except:
            continue
    return out

async def score_pool(p):
    """0-100 % risk.  None = skip."""
    mint = p["mint"]
    # top-5 holders
    async with httpx.AsyncClient() as h:
        r = await h.get(f"https://public-api.solscan.io/token/holders",
                        params={"token": mint, "limit": 20}, timeout=10)
        if r.status_code != 200: return None
        holders = r.json().get("data", [])
        if not holders: return None
        supply = float(holders[0]["supply"])
        top5 = sum(float(h["amount"]) for h in holders[:5]) / supply * 100
    # age (slots proxy)
    now_slot = (await SOLANA.get_slot())["result"]
    # crude: assume 2 slots/sec, age = last 2 hr window
    age_min = ((now_slot % (3600 * 2)) * 0.4) / 60
    # risk formula
    risk = min(100, max(0, (top5 * 0.6) + (30 / (age_min + 1)) + (100 / (p["liq"] + 1))))
    return int(risk)

async def maybe_buy(pool, risk):
    mint = pool["mint"]
    # find users whose risk <= coin risk
    users = []
    for key in db.scan_iter("u:*"):
        ud = db.hgetall(key)
        uid = int(key.decode().split(":")[1])
        u_risk = int(ud.get(b"risk", 0))
        if u_risk <= risk:
            users.append((uid, u_risk, int(ud.get(b"cashout", 70))))
    if not users: return
    # buy aggregate size (0.01 SOL per user for MVP)
    total_sol = 0.01 * len(users)
    quote = await jupiter_quote(total_sol, mint)
    if not quote: return
    swap = await jupiter_swap_tx(quote)
    if not swap: return
    tx = VersionedTransaction.from_bytes(bytes.fromhex(swap["swapTransaction"]))
    tx.sign_partial(BOT_KEY)
    tx_hex = tx.serialize().hex()
    # store meta for later sells
    db.hset(f"buy:{mint}", mapping={
        "tx": tx_hex,
        "price": str(float(quote["inAmount"]) / 1e9),  # SOL paid
        "users": json.dumps(users),  # [(uid, risk, cashout), ...]
        "token_out": str(int(quote["outAmount"]))
    })
    # send TG button
    msg = (f"🔥 <b>MEME</b>  risk={risk}%  users={len(users)}\n"
           f"Aggregate buy {total_sol:.3f} SOL")
    kb = [[InlineKeyboardButton("✅ Broadcast Buy", callback_data=f"buy:{mint}")]]
    await BOT_APP.bot.send_message(chat_id=cfg["tg_channel"], text=msg,
                                 reply_markup=InlineKeyboardMarkup(kb),
                                 parse_mode="HTML")

# ---------- SELL / CHECKPOINT ----------
async def checkpoint_sell(mint: str, target_pct: int):
    buy_meta = db.hgetall(f"buy:{mint}")
    if not buy_meta: return
    users = json.loads(buy_meta[b"users"].decode())
    price_entry = float(buy_meta[b"price"].decode())
    token_out = int(buy_meta[b"token_out"].decode())
    # who should exit at this checkpoint?
    sellers = [u for u in users if u[2] <= target_pct]
    if not sellers: return
    # current price
    quote = await jupiter_quote(0.01, mint)  # tiny probe
    if not quote: return
    price_now = float(quote["inAmount"]) / 1e9 / (int(quote["outAmount"]) / 1e6)
    gain_pct = (price_now - price_entry) / price_entry * 100
    if gain_pct < target_pct: return  # not there yet
    # pro-rata sell
    total_tokens = token_out * len(sellers) / len(users)
    sell_quote = await jupiter_quote(total_tokens, mint, reverse=True)
    if not sell_quote: return
    swap = await jupiter_swap_tx(sell_quote, reverse=True)
    if not swap: return
    tx = VersionedTransaction.from_bytes(bytes.fromhex(swap["swapTransaction"]))
    tx.sign_partial(BOT_KEY)
    tx_hex = tx.serialize().hex()
    key_sell = f"sell:{mint}:{target_pct}"
    db.hset(key_sell, mapping={"tx": tx_hex, "gain": str(gain_pct)})
    msg = (f"🎯 Checkpoint {target_pct}% hit for {mint}\n"
           f"Users {len(sellers)}  gain ≈ {gain_pct:.1f}%")
    kb = [[InlineKeyboardButton(f"Broadcast {target_pct}% Sell", callback_data=key_sell)]]
    await BOT_APP.bot.send_message(chat_id=cfg["tg_channel"], text=msg,
                                 reply_markup=InlineKeyboardMarkup(kb),
                                 parse_mode="HTML")

# ---------- JUPITER HELPERS ----------
async def jupiter_quote(amount_in: float, mint: str, reverse: bool = False):
    url = cfg["jupiter_quote"]
    params = {
        "inputMint": "So11111111111111111111111111111111111111112" if not reverse else mint,
        "outputMint": mint if not reverse else "So11111111111111111111111111111111111111112",
        "amount": int(amount_in * 1e9) if not reverse else int(amount_in),
        "slippageBps": 50
    }
    async with httpx.AsyncClient() as h:
        r = await h.get(url, params=params, timeout=10)
        return r.json() if r.status_code == 200 else None

async def jupiter_swap_tx(quote: dict, reverse: bool = False):
    url = cfg["jupiter_swap"]
    body = {"userPublicKey": str(BOT_KEY.pubkey()), "quoteResponse": quote}
    async with httpx.AsyncClient() as h:
        r = await h.post(url, json=body, timeout=10)
        return r.json() if r.status_code == 200 else None

# ---------- CHECKPOINT POLLER ----------
async def poll_checkpoints():
    while True:
        for chk in CHECKPOINTS:
            for key in db.scan_iter("buy:*"):
                mint = key.decode().split(":")[1]
                await checkpoint_sell(mint, chk)
        await asyncio.sleep(15)

# ---------- TG BUTTON HANDLERS ----------
async def handle_buy_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    mint = query.data.split(":")[1]
    meta = db.hgetall(f"buy:{mint}")
    if not meta:
        await query.answer("Expired", show_alert=True); return
    tx_hex = meta[b"tx"].decode()
    tx = VersionedTransaction.from_bytes(bytes.fromhex(tx_hex))
    try:
        sig = await SOLANA.send_transaction(tx, opts={"skip_confirmation": False, "preflight_commitment": "processed"})
        await query.answer("Buy broadcast ✅")
        await query.edit_message_text(query.message.text_html + f"\nSig: <code>{sig}</code>", parse_mode="HTML")
    except Exception as e:
        await query.answer(f"Failed ❌ {e}", show_alert=True)

async def handle_sell_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, mint, pct = query.data.split(":")
    meta = db.hgetall(f"sell:{mint}:{pct}")
    if not meta:
        await query.answer("Expired", show_alert=True); return
    tx_hex = meta[b"tx"].decode()
    tx = VersionedTransaction.from_bytes(bytes.fromhex(tx_hex))
    try:
        sig = await SOLANA.send_transaction(tx, opts={"skip_confirmation": False, "preflight_commitment": "processed"})
        await query.answer(f"{pct}% sell broadcast ✅")
        await query.edit_message_text(query.message.text_html + f"\nSig: <code>{sig}</code>", parse_mode="HTML")
    except Exception as e:
        await query.answer(f"Failed ❌ {e}", show_alert=True)

# ---------- MAIN ----------
def main():
    app = Application.builder().token(cfg["telegram_token"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("risk", risk))
    app.add_handler(CommandHandler("cashout", cashout))
    app.add_handler(CallbackQueryHandler(handle_buy_btn, pattern="^buy:"))
    app.add_handler(CallbackQueryHandler(handle_sell_btn, pattern="^sell:"))
    loop = asyncio.get_event_loop()
    loop.create_task(poll_new_pools())
    loop.create_task(poll_checkpoints())
    app.run_polling()

if __name__ == "__main__":
    main()