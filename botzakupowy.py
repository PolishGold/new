import os, time, json, requests

# === KONFIG ===
ADDRESS_BSC         = "0x1ec01b6D86Eb024d805dEd6e8e1a7B1F5f7E8f04".lower()
ADDRESS_ETH         = "0x1ec01b6D86Eb024d805dEd6e8e1a7B1F5f7E8f04".lower()   # <- podmień jeśli inny
BSCSCAN_API_KEY     = "REAC9BP8R63GIM3Z1WA2QV12PCZTS8ZEKW"
ETHERSCAN_API_KEY   = "159JVKE548VIZF8WJNTUG6DJ4HCFK8R4MF"

TELEGRAM_BOT_TOKEN  = "8217749121:AAHbdrZUjpC9vMbjCu1jNMup21i6I-KcdCk"    # stary był publiczny — zregeneruj
TELEGRAM_CHAT_ID    = "-1002277672578"

POLL_SECONDS        = 15

TOKEN_NAME          = "BabyBitcoin"
TOKEN_SYMBOL        = "BBTC"
BUY_URL             = "https://www.bitcoin-baby.com/buy"

PRICE_PER_COIN_USD  = "0.012"
LAUNCH_PRICE_USD    = "0.03"
HEADER_GIF_URL      = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExbDR3eHI0eW9kanB3ZjdiOWgyazJ3djE2b3dreDk1YWZsNmJibGloNiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/smaaKxR6ZrQYQxHFfA/giphy.gif"

FIXED_BNB_USD       = "795"     # zostaw puste "" by czytać z Coingecko
FIXED_ETH_USD       = ""        # np. "3200" jeśli chcesz stałą

# === STAŁE ===
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "multi_state.json")

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

# === STAN ===
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "BSC": {"last_tx_hash_native": None, "last_tx_hash_token": None},
            "ETH": {"last_tx_hash_native": None, "last_tx_hash_token": None},
        }

def save_state(s): 
    with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(s, f)

# === TELEGRAM ===
def send_text(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=15).raise_for_status()
    except Exception as e:
        print("Telegram error:", e)

def send_header():
    if not HEADER_GIF_URL: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendAnimation"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "animation": HEADER_GIF_URL}, timeout=20).raise_for_status()
    except Exception as e:
        print("Telegram gif error:", e)

# === CENY ===
def get_native_usd(chain_key: str) -> float:
    cfg = CHAINS[chain_key]
    if cfg["price_fixed"]:
        try: return float(cfg["price_fixed"])
        except: pass
    try:
        r = requests.get(cfg["price_url"], timeout=15).json()
        key = "binancecoin" if chain_key == "BSC" else "ethereum"
        return float(r[key]["usd"])
    except Exception as e:
        print(f"{chain_key} price error:", e); return 0.0

def wei_to_native(wei: int, chain_key: str) -> float:
    return wei / (10 ** CHAINS[chain_key]["decimals_native"])

# === POBIERANIE TX ===
def fetch_latest_native_tx(chain_key: str):
    cfg = CHAINS[chain_key]
    p = {
        "module": "account",
        "action": "txlist",
        "address": cfg["address"],
        "startblock": 0, "endblock": 99999999,
        "sort": "desc",
        "apikey": cfg["api_key"]
    }
    r = requests.get(cfg["api_base"], params=p, timeout=20).json()
    if r.get("status") != "1" or not r.get("result"): return None
    for tx in r["result"]:
        if (tx.get("to","") or "").lower() == cfg["address"]:
            return tx
    return None

def fetch_latest_token_tx(chain_key: str):
    cfg = CHAINS[chain_key]
    p = {
        "module": "account",
        "action": "tokentx",
        "address": cfg["address"],
        "startblock": 0, "endblock": 99999999,
        "sort": "desc",
        "apikey": cfg["api_key"]
    }
    r = requests.get(cfg["api_base"], params=p, timeout=20).json()
    if r.get("status") != "1" or not r.get("result"): return None
    for tx in r["result"]:
        if (tx.get("to","") or "").lower() == cfg["address"]:
            return tx
    return None

# === FORMAT WIADOMOŚCI ===
def format_msg(chain_key: str, native_amount: float, token_qty: float|None, tx_hash: str) -> str:
    cfg = CHAINS[chain_key]
    usd = get_native_usd(chain_key)
    total_usd = native_amount * usd if usd else 0.0
    coin_amount = None
    if PRICE_PER_COIN_USD:
        try:
            price = float(PRICE_PER_COIN_USD)
            coin_amount = (total_usd / price) if total_usd else None
        except: pass
    if coin_amount is None and token_qty is not None:
        coin_amount = token_qty

    rows = [
        f"🟢 <b>Presale Purchase ({chain_key})</b>",
        f"Amount: <b>{native_amount:.6f} {cfg['native_symbol']}</b>",
        (f"Coin Amount: <b>{coin_amount:,.0f} {TOKEN_SYMBOL}</b>" if coin_amount is not None else "Coin Amount: <i>—</i>"),
        (f"Purchase Total: <b>${total_usd:,.2f}</b>" if total_usd else "Purchase Total: <i>—</i>"),
    ]
    if PRICE_PER_COIN_USD:
        try: rows.append(f"Price Per Coin: <b>${float(PRICE_PER_COIN_USD):.6f}</b>")
        except: pass
    if LAUNCH_PRICE_USD:
        try: rows.append(f"Launch Price: <b>${float(LAUNCH_PRICE_USD):.6f}</b>")
        except: pass
    link = CHAINS[chain_key]["explorer"] + tx_hash
    rows += ["", f"🔵 <b>Buy {TOKEN_NAME} ({TOKEN_SYMBOL})</b>: {BUY_URL}", f"🔗 <a href=\"{link}\">Transaction</a>"]
    return "\n".join(rows)

# === PĘTLA GŁÓWNA ===
def main():
    state = load_state()
    print("Monitoring addresses:",
          "BSC:", CHAINS["BSC"]["address"],
          "ETH:", CHAINS["ETH"]["address"])
    while True:
        for chain_key in ("BSC","ETH"):
            try:
                cfg = CHAINS[chain_key]
                native_tx = fetch_latest_native_tx(chain_key)
                token_tx  = fetch_latest_token_tx(chain_key)
                chosen = native_tx or token_tx
                if not chosen: 
                    continue
                h = chosen["hash"]
                is_native = "value" in chosen  # w txlist jest pole value (wei)
                # --- NATYWNY TRANSFER ---
                if is_native and h != state[chain_key].get("last_tx_hash_native"):
                    amt = wei_to_native(int(chosen["value"]), chain_key)
                    tkn_qty = None
                    if token_tx and token_tx.get("hash")==h:
                        dec = int(token_tx.get("tokenDecimal","18") or 18)
                        tkn_qty = int(token_tx["value"]) / (10**dec)
                    send_header()
                    send_text(format_msg(chain_key, amt, tkn_qty, h))
                    state[chain_key]["last_tx_hash_native"] = h
                    save_state(state)
                # --- TOKEN TRANSFER (gdy brak natywnego matcha) ---
                if (not is_native) and h != state[chain_key].get("last_tx_hash_token"):
                    dec = int(chosen.get("tokenDecimal","18") or 18)
                    tkn_qty = int(chosen["value"]) / (10**dec)
                    send_header()
                    send_text(format_msg(chain_key, 0.0, tkn_qty, h))
                    state[chain_key]["last_tx_hash_token"] = h
                    save_state(state)
            except Exception as e:
                print(f"{chain_key} loop error:", e)
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
