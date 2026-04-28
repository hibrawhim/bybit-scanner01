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
    """Fetches all USDT Perpetual pairs on Bybit."""
    try:
        resp = session.get_instruments_info(category=SYMBOL_CATEGORY)
        return [i['symbol'] for i in resp['result']['list'] if i['quoteCoin'] == 'USDT' and i['status'] == 'Trading']
    except Exception as e:
        print(f"Error fetching symbols: {e}")
        return []

def send_telegram(message):
    """Sends signal to your Telegram Bot."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def scan():
    symbols = get_symbols()
    print(f"Starting scan for {len(symbols)} symbols...")
    
    for symbol in symbols:
        try:
            # Fetch last 50 candles for indicator stability
            kline = session.get_kline(category=SYMBOL_CATEGORY, symbol=symbol, interval=TIMEFRAME, limit=50)
            df = pd.DataFrame(kline['result']['list'], columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turnover'])
            df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].apply(pd.to_numeric)
            df = df.iloc[::-1].reset_index(drop=True) 

            # --- Technical Indicators ---
            df['sma_h'] = ta.sma(df['high'], length=7)
            df['sma_l'] = ta.sma(df['low'], length=7)
            
            # Hammer & Rejection Logic
            df['body'] = (df['close'] - df['open']).abs()
            df['tr'] = df['high'] - df['low']
            df['is_ham'] = (df['body'] > 0) & ((df['tr'] / df['body']) > 2.0)
            
            # Extract current and previous rows
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Clean State Check (Bodies outside channel)
            is_clean_below_prev = (prev['open'] < prev['sma_l']) and (prev['close'] < prev['sma_l'])
            is_clean_above_prev = (prev['open'] > prev['sma_h']) and (prev['close'] > prev['sma_h'])
            
            # Trigger logic: Price was "Clean" outside, now it "Rejects" (wicks back into channel)
            # Bear Rejection: Previous candle was clean below, current high touches/crosses sma_l
            bear_reject = is_clean_below_prev and curr['high'] > prev['sma_l']
            
            # Bull Rejection: Previous candle was clean above, current low touches/crosses sma_h
            bull_reject = is_clean_above_prev and curr['low'] < prev['sma_h']

            if bear_reject:
                send_telegram(f"🔴 *BEAR REJECTION*: {symbol}\nTimeframe: 1H\nPrice rejected lower channel boundary.")
                print(f"Signal found: {symbol} BEAR")
                
            if bull_reject:
                send_telegram(f"🟢 *BULL REJECTION*: {symbol}\nTimeframe: 1H\nPrice rejected upper channel boundary.")
                print(f"Signal found: {symbol} BULL")

        except Exception as e:
            continue # Skip errors to keep the scanner moving

if __name__ == "__main__":
    scan()
