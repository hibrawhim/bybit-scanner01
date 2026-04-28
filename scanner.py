import os
import requests
import pandas as pd
import pandas_ta_classic as ta
from pybit.unified_trading import HTTP

# --- Configuration ---
SYMBOL_CATEGORY = "linear"
TIMEFRAME = "60"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

session = HTTP(testnet=False)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Failed: {e}")

def scan():
    send_telegram("🔍 *Scanner Online*: Checking 1H Confirmed Bars...")
    
    resp = session.get_instruments_info(category=SYMBOL_CATEGORY)
    # Error Handling for Symbol List
    if resp.get('retCode') != 0:
        print(f"Bybit API Error (Symbols): {resp.get('retCode')} - {resp.get('retMsg')}")
        return

    symbols = [i['symbol'] for i in resp['result']['list'] if i['quoteCoin'] == 'USDT' and i['status'] == 'Trading']
    print(f"Scanning {len(symbols)} symbols...")

    for symbol in symbols:
        try:
            kline = session.get_kline(category=SYMBOL_CATEGORY, symbol=symbol, interval=TIMEFRAME, limit=50)
            
            # Error Handling for Kline Data
            if kline.get('retCode') != 0:
                print(f"Skipping {symbol}: {kline.get('retMsg')} (Code: {kline.get('retCode')})")
                continue

            df = pd.DataFrame(kline['result']['list'], columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turnover'])
            df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].apply(pd.to_numeric)
            df = df.iloc[::-1].reset_index(drop=True) 

            # Indicators
            df['sma_h'] = ta.sma(df['high'], length=7)
            df['sma_l'] = ta.sma(df['low'], length=7)
            
            # Hammer logic
            df['body'] = (df['close'] - df['open']).abs()
            df['tr'] = df['high'] - df['low']
            df['is_ham'] = (df['body'] > 0) & ((df['tr'] / df['body']) > 2.0)
            
            # --- SHIFT TO CONFIRMED BARS ---
            # index -1 = Live bar (ignore)
            # index -2 = Last Confirmed Bar (The Signal Bar)
            # index -3 = The "Setup" Bar
            confirmed = df.iloc[-2]
            setup = df.iloc[-3]
            
            # Logic: Setup was "Clean" outside, Confirmed bar "Rejects" back
            is_clean_below_setup = (setup['open'] < setup['sma_l']) and (setup['close'] < setup['sma_l'])
            is_clean_above_setup = (setup['open'] > setup['sma_h']) and (setup['close'] > setup['sma_h'])
            
            bear_reject = is_clean_below_setup and confirmed['high'] > setup['sma_l']
            bull_reject = is_clean_above_setup and confirmed['low'] < setup['sma_h']

            if bear_reject:
                send_telegram(f"🔴 *BEAR REJECTION*: {symbol}\nTime: {confirmed['ts']}\nType: Confirmed 1H Close")
                print(f"MATCH: {symbol} BEAR")
            if bull_reject:
                send_telegram(f"🟢 *BULL REJECTION*: {symbol}\nTime: {confirmed['ts']}\nType: Confirmed 1H Close")
                print(f"MATCH: {symbol} BULL")

        except Exception as e:
            print(f"System Error on {symbol}: {str(e)}")

if __name__ == "__main__":
    scan()
