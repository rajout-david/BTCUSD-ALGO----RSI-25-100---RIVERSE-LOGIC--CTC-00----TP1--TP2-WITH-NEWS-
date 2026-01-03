from flask import Flask, request, jsonify
import logging
from trade_executer import close_positions_of_this_pair, logic_processing_here, ctc_for_all_pairs, sl_tp_manager
import json
import threading
import re
import time
from datetime import datetime, date
from news import extract_news_interval, wait_if_between_news_period
from filelock import FileLock



lock_pairs_signal = FileLock("pairs_signal.json.lock")

with open("cred.json", 'r') as file:
    cred = json.load(file)

SYMBOL_ADD_ONS = cred['user1']['symbol_addons']

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        raw_data = request.get_data(as_text=True)
        print(raw_data)

        pattern = r"order\s+(buy|sell).*?\b([A-Z]+[A-Z0-9]*)\b"

        match = re.search(pattern, raw_data, re.IGNORECASE)

        if match:
            trade_side = match.group(1).lower()  # buy or sell
            match = re.search(r"\bon\s+([A-Z]{3,})\b", raw_data)
            symbol = match.group(1) if match else None

        print(trade_side, symbol)


        symbol_ = symbol + SYMBOL_ADD_ONS
        close_positions_of_this_pair(symbol=symbol_, cut_riverse=False)

        with open("pairs_signal.json", "r") as ps:
            signal_store = json.load(ps)

        signal_store[symbol_] = trade_side

        with lock_pairs_signal:

            with open("pairs_signal.json", "w") as ps:
                json.dump(signal_store, ps, indent=1)


        if trade_side == "buy":
            process_signal = threading.Thread(target=logic_processing_here(symbol=symbol, trade_side="buy"), daemon=True)
            process_signal.start()
            return jsonify({"status": "success", "message": "Trade command processed"}), 200

        elif trade_side == "sell":
            process_signal = threading.Thread(target=logic_processing_here(symbol=symbol, trade_side="sell"), daemon=True)
            process_signal.start()
            return jsonify({"status": "success", "message": "Trade command processed"}), 200
        

        return jsonify({"status": "success", "data": raw_data})

        
    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 400
    

@app.route('/')
def home():
    return "Webhook Receiver Running!", 200

if __name__ == '__main__':
    with open("cred.json", 'r') as file:
        cred = json.load(file)
    port = cred['user1']['port']
    print(f"port is:: {port}")
    updater_thread1 = threading.Thread(target=sl_tp_manager, daemon=True)
    updater_thread1.start()
    updater_thread2 = threading.Thread(target=ctc_for_all_pairs, daemon=True)
    updater_thread2.start()
    app.run(host='0.0.0.0', port=port, debug=False)
