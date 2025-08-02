# bot.py
import os
import json
import requests
from telegram import Bot, Update
from telegram.ext import Dispatcher, MessageHandler, Filters, CallbackContext

# — KONFIG z ENV —
ADDRESS_BSC         = os.getenv("ADDRESS_BSC")
ADDRESS_ETH         = os.getenv("ADDRESS_ETH")
BSCSCAN_API_KEY     = os.getenv("BSCSCAN_API_KEY")
ETHERSCAN_API_KEY   = os.getenv("ETHERSCAN_API_KEY")
TELEGRAM_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID")
POLL_SECONDS        = int(os.getenv("POLL_SECONDS", "15"))
TOKEN_NAME          = os.getenv("TOKEN_NAME")
TOKEN_SYMBOL        = os.getenv("TOKEN_SYMBOL")
BUY_URL             = os.getenv("BUY_URL")
PRICE_PER_COIN_USD  = os.getenv("PRICE_PER_COIN_USD")
LAUNCH_PRICE_USD    = os.getenv("LAUNCH_PRICE_USD")
HEADER_GIF_URL      = os.getenv("HEADER_GIF_URL")
FIXED_BNB_USD       = os.getenv("FIXED_BNB_USD", "")
FIXED_ETH_USD       = os.getenv("FIXED_ETH_USD", "")

COINGECKO_BNB = "https://api.coingecko.com/api/v3/simple/price?ids=binancecoin&vs_currencies=usd"
COINGECKO_ETH = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"

CHAINS = {
    "BSC": {
        "address": ADDRESS_BSC,
        "api_base": "https://api.bscscan.com/api",
        "api_key": BSCSCAN_API_KEY,
        "explorer": "https://bscscan.com/tx/",
        "native_symbol": "BNB",
        "price_fixed": FIXED_BNB_USD,
        "price_url": COINGECKO_BNB,
        "decimals_native": 18,
    },
    "ETH": {
        "address": ADDRESS_ETH,
        "api_base": "https://api.etherscan.io/api",
        "api_key": ETHERSCAN_API_KEY,
        "explorer": "https://etherscan.io/tx/",
        "native_symbol": "ETH",
        "price_fixed": FIXED_ETH_USD,
        "price_url": COINGECKO_ETH,
        "decimals_native": 18,
    },
}

STATE_FILE = "state.json"
bot = Bot(token=TELEGRAM_TOKEN)

def load_state():
    try:
        return json.load(open(STATE_FILE, "r"))
    except:
        return {
            "BSC": {"last_tx_hash_native": None, "last_tx_hash_token": None},
            "ETH": {"last_tx_hash_native": None, "last_tx_hash_token": None},
        }

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f)

def send_text(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    })

def send_header():
    if not HEADER_GIF_URL:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendAnimation"
    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "animation": HEADER_GIF_URL
    })

def get_native_usd(chain_key: str) -> float:
    cfg = CHAINS[chain_key]
    if cfg["price_fixed"]:
        try:
            return float(cfg["price_fixed"])
        except:
            pass
    try:
        r = requests.get(cfg["price_url"], timeout=15).json()
        key = "binancecoin" if chain_key == "BSC" else "ethereum"
        return float(r[key]["usd"])
    except:
        return 0.0

def wei_to_native(wei: int, chain_key: str) -> float:
    return wei / (10 ** CHAINS[chain_key]["decimals_native"])

def fetch_latest_native_tx(chain_key: str):
    cfg = CHAINS[chain_key]
    params = {
        "module": "account",
        "action": "txlist",
        "address": cfg["address"],
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "apikey": cfg["api_key"]
    }
    r = requests.get(cfg["api_base"], params=params, timeout=20).json()
    if r.get("status") != "1" or not r.get("result"):
        return None
    for tx in r["result"]:
        if (tx.get("to") or "").lower() == cfg["address"]:
            return tx
    return None

def fetch_latest_token_tx(chain_key: str):
    cfg = CHAINS[chain_key]
    params = {
        "module": "account",
        "action": "tokentx",
        "address": cfg["address"],
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "apikey": cfg["api_key"]
    }
    r = requests.get(cfg["api_base"], params=params, timeout=20).json()
    if r.get("status") != "1" or not r.get("result"):
        return None
    for tx in r["result"]:
        if (tx.get("to") or "").lower() == cfg["address"]:
            return tx
    return None

def format_msg(chain_key: str, native_amount: float, token_qty: float | None, tx_hash: str) -> str:
    cfg = CHAINS[chain_key]
    usd_price = get_native_usd(chain_key)
    total_usd = native_amount * usd_price if usd_price else 0.0

    # Determine BBTC amount
    coin_amount = None
    if PRICE_PER_COIN_USD:
        try:
            per = float(PRICE_PER_COIN_USD)
            coin_amount = total_usd / per if total_usd else None
        except:
            pass
    if coin_amount is None and token_qty is not None:
        coin_amount = token_qty

    lines = [
        f"🟢 <b>Presale Purchase ({chain_key})</b>",
        f"Amount: <b>{native_amount:.6f} {cfg['native_symbol']}</b>",
        (f"Coin Amount: <b>{coin_amount:,.0f} {TOKEN_SYMBOL}</b>" if coin_amount is not None else "Coin Amount: <i>—</i>"),
        (f"Purchase Total: <b>${total_usd:,.2f}</b>" if total_usd else "Purchase Total: <i>—</i>"),
    ]
    if PRICE_PER_COIN_USD:
        try:
            lines.append(f"Price Per Coin: <b>${float(PRICE_PER_COIN_USD):.6f}</b>")
        except:
            pass
    if LAUNCH_PRICE_USD:
        try:
            lines.append(f"Launch Price: <b>${float(LAUNCH_PRICE_USD):.6f}</b>")
        except:
            pass

    tx_link = cfg["explorer"] + tx_hash
    lines += [
        "",
        f"🔵 <b>Buy {TOKEN_NAME} ({TOKEN_SYMBOL})</b>: {BUY_URL}",
        f"🔗 <a href=\"{tx_link}\">View Transaction</a>"
    ]
    return "\n".join(lines)

def run_once():
    state = load_state()
    for chain in ("BSC", "ETH"):
        native_tx = fetch_latest_native_tx(chain)
        token_tx  = fetch_latest_token_tx(chain)
        chosen = native_tx or token_tx
        if not chosen:
            continue

        h = chosen["hash"]
        is_native = bool(native_tx and native_tx["hash"] == h)

        # Native-transfer notification
        if is_native and h != state[chain].get("last_tx_hash_native"):
            amt = wei_to_native(int(native_tx["value"]), chain)
            tkn = None
            if token_tx and token_tx.get("hash") == h:
                dec = int(token_tx.get("tokenDecimal", "18") or 18)
                tkn = int(token_tx["value"]) / (10 ** dec)
            send_header()
            send_text(format_msg(chain, amt, tkn, h))
            state[chain]["last_tx_hash_native"] = h

        # Token-transfer notification (if no native match)
        if not is_native and h != state[chain].get("last_tx_hash_token"):
            dec = int(chosen.get("tokenDecimal", "18") or 18)
            tkn = int(chosen["value"]) / (10 ** dec)
            send_header()
            send_text(format_msg(chain, 0.0, tkn, h))
            state[chain]["last_tx_hash_token"] = h

    save_state(state)

if __name__ == "__main__":
    run_once()
