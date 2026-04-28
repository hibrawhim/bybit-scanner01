import os
import requests
import pandas as pd
import pandas_ta as ta
from pybit.unified_trading import HTTP

# --- Configuration ---
SYMBOL_CATEGORY = "linear"  # USDT Perpetual
TIMEFRAME = "60"            # 1 Hour
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

session = HTTP(testnet=False)

def get_symbols():
    resp = session.get_instruments_info(category=SYMBOL_CATEGORY)
    return [i['symbol'] for i in resp['result']['list'] if i['quoteCoin'] == 'USDT']

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def scan():
    symbols = get_symbols()
    for symbol in symbols:
        try:
            # Fetch last 50 candles to ensure indicators stabilize
            kline = session.get_kline(category=SYMBOL_CATEGORY, symbol=symbol, interval=TIMEFRAME, limit=50)
            df = pd.DataFrame(kline['result']['list'], columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turnover'])
            df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].apply(pd.to_numeric)
            df = df.iloc[::-1].reset_index(drop=True) # Reverse to chronological

            # --- Logic Translation ---
            df['sma_h'] = ta.sma(df['high'], length=7)
            df['sma_l'] = ta.sma(df['low'], length=7)
            
            # Hammer Components
            df['body'] = (df['close'] - df['open']).abs()
            df['tr'] = df['high'] - df['low']
            df['is_ham'] = (df['body'] > 0) & ((df['tr'] / df['body']) > 2.0)
            df['mid'] = df['low'] + (df['tr'] / 2)
            
            # State Emulation (simplified for latest signals)
            # We check the last 2 candles to detect the "Rejection" trigger
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Logic for Rejection: valid_exit[1] and cross back
            # Note: Complex state memory is handled via candle history
            is_clean_below_prev = (prev['open'] < prev['sma_l']) and (prev['close'] < prev['sma_l'])
            is_clean_above_prev = (prev['open'] > prev['sma_h']) and (prev['close'] > prev['sma_h'])
            
            # Rejection Signals
            bear_reject = is_clean_below_prev and curr['high'] > prev['sma_l']
            bull_reject = is_clean_above_prev and curr['low'] < prev['sma_h']

            if bear_reject:
                send_telegram(f"🔴 *Bearish Rejection*: {symbol} (1H)")
            if bull_reject:
                send_telegram(f"🟢 *Bullish Rejection*: {symbol} (1H)")

        except Exception as e:
            print(f"Error scanning {symbol}: {e}")

if __name__ == "__main__":
    scan()
