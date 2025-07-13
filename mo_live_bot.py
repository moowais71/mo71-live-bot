import time
import csv
from ib_insync import IB, Stock
import requests
from flask import Flask
import threading

# CONFIGURATION
IB_HOST = '127.0.0.1'
IB_PORT = 7497
CLIENT_ID = 1

CAPITAL_PER_TRADE = 50
TAKE_PROFIT_PCT = 0.03
STOP_LOSS_PCT = 0.02
SCAN_INTERVAL_SEC = 15

TELEGRAM_TOKEN = '7825252778:AAGfC4xN3jBAob7sbr1SU5gi8oQGtFO6kHo'
TELEGRAM_CHAT_ID = 6534666238

STOCKS = ['AAPL', 'TSLA', 'AMD', 'NVDA', 'MSFT', 'GOOG', 'AMZN', 'META']

def send_telegram_message(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def log_trade(symbol, action, price, quantity, pnl=None):
    with open('trades.csv', 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), symbol, action, price, quantity, pnl if pnl else ''])

class MoTrader:
    def __init__(self):
        self.ib = IB()
        self.positions = {}
        self.ib.connect(IB_HOST, IB_PORT, CLIENT_ID)
        print("Connected to IB Gateway")

    def in_market_hours(self):
        import datetime
        now = datetime.datetime.utcnow()
        weekday = now.weekday()
        hour = now.hour
        minute = now.minute
        # US market open 13:30 to 20:00 UTC (9:30AM-4PM EST)
        if weekday < 5 and (hour > 13 or (hour == 13 and minute >= 30)) and hour < 20:
            return True
        return False

    def scan_and_trade(self):
        for sym in STOCKS:
            if sym in self.positions:
                self.check_exit(sym)
            else:
                self.check_entry(sym)

    def check_entry(self, symbol):
        contract = Stock(symbol, 'SMART', 'USD')
        self.ib.qualifyContracts(contract)
        ticker = self.ib.reqMktData(contract, '', False, False)
        self.ib.sleep(2)
        price = ticker.last
        prev_close = ticker.close
        if price is None or prev_close is None:
            return
        if price > prev_close * 1.003:
            qty = int(CAPITAL_PER_TRADE / price)
            if qty <= 0:
                return
            order = self.ib.bracketOrder('BUY', qty, price, price*(1+TAKE_PROFIT_PCT), price*(1-STOP_LOSS_PCT))
            for o in order:
                self.ib.placeOrder(contract, o)
            self.positions[symbol] = {'qty': qty, 'entry': price}
            msg = f"🟢 Bought {qty} shares of {symbol} at ${price:.2f}"
            print(msg)
            send_telegram_message(msg)
            log_trade(symbol, 'BUY', price, qty)

    def check_exit(self, symbol):
        contract = Stock(symbol, 'SMART', 'USD')
        self.ib.qualifyContracts(contract)
        ticker = self.ib.reqMktData(contract, '', False, False)
        self.ib.sleep(2)
        price = ticker.last
        if price is None:
            return
        pos = self.positions[symbol]
        entry = pos['entry']
        qty = pos['qty']
        pnl_pct = (price - entry) / entry
        if pnl_pct >= TAKE_PROFIT_PCT or pnl_pct <= -STOP_LOSS_PCT:
            order = self.ib.marketOrder('SELL', qty)
            self.ib.placeOrder(contract, order)
            msg = f"🔴 Sold {qty} shares of {symbol} at ${price:.2f} | PnL: {pnl_pct*100:.2f}%"
            print(msg)
            send_telegram_message(msg)
            log_trade(symbol, 'SELL', price, qty, pnl_pct*100)
            del self.positions[symbol]

    def run(self):
        while True:
            if self.in_market_hours():
                self.scan_and_trade()
            else:
                print("Market closed. Waiting...")
            time.sleep(SCAN_INTERVAL_SEC)

# Flask web server to keep Railway app alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Mo Trading Bot is running."

def start_bot():
    trader = MoTrader()
    trader.run()

if __name__ == '__main__':
    threading.Thread(target=start_bot).start()
    app.run(host='0.0.0.0', port=3000)
