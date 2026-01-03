import json
import MetaTrader5 as mt5
import time
from datetime import datetime, timedelta, timezone, date
import pytz
import sys
import pandas as pd
from loggingg import get_logger
from news import wait_if_between_news_period, extract_news_interval
from filelock import FileLock

lock_pairs_signal = FileLock("pairs_signal.json.lock")
lock_entry_prices = FileLock("entry_prices_tv.json.lock")
lock_leg_store = FileLock("store_first_leg.json.lock")
logger = get_logger()


USD_PIP_INTO_DOLLAR = 0.0001
JPY_PIP_INTO_DOLLAR = 0.01
CAD_PIP_INTO_DOLLAR = 0.0001
NZD_PIP_INTO_DOLLAR =  0.0001
AUD_PIP_INTO_DOLLAR =  0.0001
BTC_PIP_INTO_DOLLAR = 1




pairs_interval_mapping = {
    "GBPAUD": "30m",
    "CHFJPY": "30m",
    "GBPNZD": "30m",
    "GBPCAD": "30m",
    "GBPUSD": "30m",
    "EURCAD": "30m",
    "GBPJPY": "15m",
    "EURJPY": "15m",
    "AUDJPY": "30m",
    "BTCUSD": "30m"
}




def round_to_nearest_2(x):
    return round(x / 2) * 2

with open("cred.json", 'r') as file:
    cred = json.load(file)

ACCOUNT = cred['user1']['account']
SYMBOL_ADD_ONS = cred['user1']['symbol_addons']

INDIA_TZ = pytz.timezone('Asia/Kolkata')
CRED_FILE = "cred.json"
SYMBOL_REAL = cred['user1']['symbol']
REQUIRED_LOSS_FOR_RIVERSE = cred['user1']['loss_threshold']
MINUTES_WAIT_AFTER_RIVERSE = cred['user1']['minutes_wait_for_riversal']

def get_current_ist_time():
    return datetime.now(INDIA_TZ)



def execute_on_exness_mt5(symbol, side, sl, tp, riverse = False):
    try:
        if not mt5.initialize(path=f"C:/Program Files/MetaTrader 5_{ACCOUNT}/terminal64.exe"):
            logger.info("MT5 initialization failed")
            logger.info(f"Error code: {mt5.last_error()}")
            return False

        with open("cred.json", 'r') as file:
            cred = json.load(file)

        for index, (key, value) in enumerate(cred.items(), start=1):
            account_number = value['account_number']
            password = value['password']
            server = value['server']
            lot_size = value['lot_size']
            partial_lot_size = value['partial_lot_size']

            if riverse == True:
                pass
            else:
                lot_size = lot_size + partial_lot_size


            authorized = mt5.login(account_number, password, server)
            if not authorized:
                logger.info(f"Login failed for account {account_number}, Error: {mt5.last_error()}")
                continue

            logger.info(f"Logged in to account {account_number}")

            if side == "buy":                                   #this is for normal trade
                trade_type = mt5.ORDER_TYPE_BUY

            elif side == "sell":
                trade_type = mt5.ORDER_TYPE_SELL

            filling_modes = [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]

            for fill_mode in filling_modes:
                try:
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": symbol,
                        "volume": lot_size,
                        "type": trade_type,
                        "deviation": 5,
                        "magic": 0,
                        "comment": "second leg" if riverse else "First leg",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": fill_mode,
                    }

                    result = mt5.order_send(request)

                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(f"Market order placed successfully with filling mode {fill_mode}: {result}")
                        time.sleep(0.4)
                        cred[key]['order_ticket'] = result.order
                        with open("cred.json", "w") as file:
                            json.dump(cred, file, indent=4)

                        ticket = result.order
                        position = mt5.positions_get(ticket=ticket)

                        if position:
                            position = position[0]
                            entry_price = position.price_open

                            if side == "buy":
                                sl = entry_price - sl
                                tp = entry_price + tp
                            elif side == "sell":
                                sl = entry_price + sl
                                tp = entry_price - tp


                            sl = round(float(sl), 2)
                            tp = round(float(tp), 2)

                            print(sl)
                            print(tp)


                            request = {
                                "action": mt5.TRADE_ACTION_SLTP,
                                "position": ticket,
                                "symbol": symbol,
                                "sl": sl,
                                "tp": tp,
                                "magic": 0,
                                "comment": "SL/TP set for order",
                            }

                            result = mt5.order_send(request)
                            print(result)
                            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                                logger.info("sl is placed!")
                                return True

                            else:
                                logger.info("not sl placed")
                                return True
            
                  
                    elif result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
                        logger.info(f"Filling mode {fill_mode} unsupported for {symbol}, trying next...")
                        continue

                    else:
                        logger.info(f"Order failed with filling mode {fill_mode}: {result.comment}, {result}")

                except Exception as e:
                    logger.info(f"Retrying trade due to error: {e}")

            logger.info("all filling modes finished!")
            return False

    except Exception as e:
        logger.info(f"Error in execute_on_exness_mt5: {str(e)}")
        return False



def close_positions_of_this_pair(symbol, partial_close = False, cut_riverse = False):
    try:
        print("inside")
        with open("cred.json", 'r') as file:
            cred = json.load(file)

        cred = cred['user1']
        login = cred['account_number']
        server = cred['server']
        password = cred['password']
        account = cred['account']
        partial_close_lot = cred['partial_lot_size']



        if not mt5.initialize(path=f"C:/Program Files/MetaTrader 5_{account}/terminal64.exe",
                            login=login, server=server, password=password):
            logger.info("initialize() failed, error code")

            return
    
        

        if not mt5.login(login, password, server):
            logger.info("Login failed")
            return

        positions = mt5.positions_get()
        if not positions:
            logger.info("No open positions to close.")
            return

        filling_modes = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]

        for pos in positions:
            if not cut_riverse:
                if pos.comment == "second leg":
                    return True

            action = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).bid if action == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(pos.symbol).ask
            
            logger.info(f"{pos.symbol}")
            if pos.symbol == symbol:

                if not partial_close and not cut_riverse:
                    now_time = datetime.now().isoformat()
                    pnl = pos.profit
                    if pos.type == mt5.ORDER_TYPE_BUY:
                        side = "BUY"
                    elif pos.type == mt5.ORDER_TYPE_SELL:
                        side = "SELL"
                    comment = pos.comment

                    first_leg_info = {
                        "pos_close_time": now_time,
                        "pnl": pnl,
                        "side": side,
                        "comment": comment,
                        "symbol": symbol,
                        "lot_size": pos.volume
                    }

                    with lock_leg_store:
                        with open("store_first_leg.json", "w") as pos_store_file:
                            json.dump(first_leg_info, pos_store_file,  indent=4)

                else:
                    pass
            

                for attempt in range(1, 5):  # Retry up to 4 times
                    logger.info(f"Close attempt {attempt}/4 for position {pos.ticket}...")
                    for fill_mode in filling_modes:
                        close_request = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": pos.symbol,
                            "volume": pos.volume if not partial_close else partial_close_lot,
                            "type": action,
                            "position": pos.ticket,
                            "price": price,
                            "deviation": 20,
                            "magic": 1000,
                            "comment": "Auto close all",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": fill_mode,
                        }

                        result = mt5.order_send(close_request)

                        if result.retcode == mt5.TRADE_RETCODE_DONE:
                            logger.info(f"Closed position for: {symbol}")
                            return True
                        
                        elif result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
                            logger.info(f"Filling mode {fill_mode} unsupported for {pos.symbol}, trying next...")
                            continue

                        else:
                            logger.info(f"Failed with fill mode {fill_mode}: {result.comment} (Code: {result.retcode})")

                    else:
                        logger.info("Retrying with next attempt...")
                        continue  # Retry outer loop

            else:
                pass
    
    except Exception as e:
        print(f"error is: {e}")
        logger.info(f"Error inside close position function: {e}")




def riverse_trade_master():
    try:
        while True:
            time.sleep(2)

            with lock_leg_store:
                with open("store_first_leg.json", "r") as store_pos_file:
                    pos_file = json.load(store_pos_file)

                try:
                    closing_time = pos_file['pos_close_time']
                    pnl = pos_file['pnl']
                    side = pos_file['side']
                    comment = pos_file['comment']
                    symbol = pos_file['symbol']
                    lot_size = pos_file['lot_size']

                except KeyError:
                    continue


            now_time = datetime.now().isoformat()
            closing_time_dt = datetime.fromisoformat(closing_time)
            now_time_dt = datetime.fromisoformat(now_time)

            time_diff = now_time_dt - closing_time_dt
            seconds = time_diff.total_seconds()
            minutes = int(seconds / 60)

            if minutes > MINUTES_WAIT_AFTER_RIVERSE and minutes < 12 and pnl < REQUIRED_LOSS_FOR_RIVERSE:
                riverse_trade_side = "sell" if side == "buy" else "buy"
                points = 100 / lot_size
                wait_if_between_news_period(fetch_news=True)
                execute_on_exness_mt5(symbol=symbol, side=riverse_trade_side, sl= 1000, tp=points, riverse=True )

                pos_file = {}

                with lock_leg_store:
                    with open("store_first_leg.json", "w") as store_pos_file:
                        json.dump(pos_file, store_pos_file)
              
    except Exception as e:
        logger.info("")


def riverse_position_monitoring():
    try:
        while True:
            with lock_pairs_signal:
                with open("pairs_logic.json", "r") as file:
                    inputs = json.load(file)

                interval_of_pair = inputs['pairs_interval_mapping']
                interval = interval_of_pair[SYMBOL_REAL]

            diff_seconds, multiplier = seconds_to_next_interval(interval)
            time.sleep(diff_seconds + 10)

            trade_side, comment = running_pos_trade_side_comm()
            trade_side = trade_side.lower()

            if comment == "second leg":
                with lock_pairs_signal:
                    with open("pairs_signal.json", "r") as ps:
                        signal_store = json.load(ps)

                    signal_store_dt = signal_store[SYMBOL_REAL]

                    if signal_store_dt != trade_side:
                        logger.info(f"signal changed to:{trade_side} to {signal_store_dt} closing the thread~")
                        close_positions_of_this_pair(symbol=SYMBOL_REAL, cut_riverse=True) 

            else:
                logger.info("this is first leg im from riverse pos manager") 

    except Exception as e:
        logger.info(f"Error inside riverse position monitoring func: {e}")



def do_ctc(ticket, breakeven):
    try:
        with open("cred.json", 'r') as file:
            cred = json.load(file)

        info = cred['user1']
        login = info['account_number']
        server = info['server']
        password = info['password']

        for index, (key, value) in enumerate(cred.items(), start=1):
            account_number = value['account_number']
            password = value['password']
            server = value['server']
            account = value['account']

            if not mt5.initialize(path=f"C:/Program Files/MetaTrader 5_{account}/terminal64.exe",login=login, server=server,password=password):
                print(f"initialize() failed, error code:")
                quit()

            authorized = mt5.login(account_number, password, server)

            if authorized:
                position = mt5.positions_get(ticket=ticket)

            
                if position is None or len(position) == 0:
                    print(f"No position found with ticket: {ticket}")
                    return

                position = position[0]  
                symbol = position.symbol
                tp = position.tp
                
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": symbol,
                    "position": ticket,
                    "magic": 234000,
                    "comment": "",
                    "sl": breakeven,
                    "tp": tp
                }

                result = mt5.order_send(request)

                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    pass
                else:
                    print(f"SL modified successfully for ticket {ticket}, new SL: {breakeven}")

            else:
                print("Failed to connect to account")
    
    except Exception as e:
        pass




def ctc_for_all_pairs():
        with open("cred.json", 'r') as file:
            cred = json.load(file)

        cred = cred['user1']
        login = cred['account_number']
        server = cred['server']
        password = cred['password']
        account = cred['account']
        symbol = cred['symbol']
        lot_size = cred['lot_size']
        partial_lot_size = cred['partial_lot_size']
        lott = lot_size + partial_lot_size
        lott = round(lott, 2)

        if not mt5.initialize(path=f"C:/Program Files/MetaTrader 5_{account}/terminal64.exe",
                            login=login, server=server, password=password):
            logger.info("initialize() failed, error code =")
            return

        if not mt5.login(login, password, server):
            logger.info("Login failed")
            return
        
        with open("pairs_logic.json", "r") as file:
            inputs = json.load(file)

        ctc_mapping = inputs['pairs_ctc_mapping']
        print("Ctc Agent is running...", flush=True)
        interval_of_pair = inputs['pairs_interval_mapping']
        inter = str(interval_of_pair[f'{SYMBOL_REAL}']) + "m"

        tickets = []
        
        while True:
            try:
                with lock_entry_prices:
                    with open("entry_prices_tv.json", "r") as e_p:
                        dttt = json.load(e_p)

                entry_price = dttt[symbol]
                time.sleep(1)
                logger.info("Ctc Agent is running...")
                positions = mt5.positions_get()
                df = get_forex_history(pair=symbol, interval= inter)
                candle_dt = df.iloc[-1]
                signal_candle_high = candle_dt['high']
                signal_candle_low = candle_dt['low']

                for pos in positions:
                    if pos.comment == "second leg":
                        continue

                    if pos.ticket in tickets:
                        continue

                    symbol_ = pos.symbol

                    if symbol != symbol_:
                        continue
                    symbol = pos.symbol

                    order_type = pos.type 
                    tick = mt5.symbol_info_tick(symbol)


                    if order_type == mt5.ORDER_TYPE_BUY:
                        side = "buy"
                    elif order_type == mt5.ORDER_TYPE_SELL:
                        side = "sell"


                    if "BTCUSD" in symbol:
                        pips_to_points = 1
                        ctc_point = ctc_mapping[symbol] * pips_to_points

                    else:
                        pips_to_points = globals()[f"{symbol}_PIP_INTO_DOLLAR"]
                        ctc_point = ctc_mapping[symbol] * pips_to_points


                    if ctc_point == 0:
                        continue


                    if side == "buy":
                        ctc_do_level = entry_price + ctc_point
                        logger.info(f"{symbol} ctc is level is: {ctc_do_level}")

                        if signal_candle_high >= ctc_do_level:
                            tickets.append(pos.ticket)

                            with open("pairs_logic.json", "r") as file:
                                inputs = json.load(file)

                            distance = inputs['shift_sl_distance_from_entry']
                            inputs['pairs_stoploss_mapping_real'][symbol] = distance
                            
                            with open("pairs_logic.json", "w") as file:
                                json.dump(inputs, file, indent=4)


                            account_lot_size = running_pos_lot_size()

                            if account_lot_size == lott:
                                close_positions_of_this_pair(symbol=symbol, partial_close=True)



                    elif side == "sell":
                        ctc_do_level = entry_price - ctc_point
                        logger.info(f"{symbol} ctc is level is: {ctc_do_level}")

                        if signal_candle_low <= ctc_do_level:
                            tickets.append(pos.ticket)
                            with open("pairs_logic.json", "r") as file:
                                inputs = json.load(file)

                            distance = inputs['shift_sl_distance_from_entry']
                            inputs['pairs_stoploss_mapping_real'][symbol] = distance
                            
                            with open("pairs_logic.json", "w") as file:
                                json.dump(inputs, file, indent=4)

                            account_lot_size = running_pos_lot_size()

                            if account_lot_size == lott:
                                close_positions_of_this_pair(symbol=symbol, partial_close=True)



            except Exception as e:
                logger.info(f"Error in side ctc for all pairs!: {e}")

                if not mt5.initialize(path=f"C:/Program Files/MetaTrader 5_{account}/terminal64.exe",
                                    login=login, server=server, password=password):
                    logger.info("initialize() failed, error code =")


                if not mt5.login(login, password, server):
                    logger.info("Login failed")

                import traceback
                traceback.print_exc()

                time.sleep(1)


def sl_tp_manager():
        with open("cred.json", 'r') as file:
            cred = json.load(file)

        cred = cred['user1']
        login = cred['account_number']
        server = cred['server']
        password = cred['password']
        account = cred['account']
        symbol = cred['symbol']
        partial_lot_size = cred['partial_lot_size']
        lot_size = cred['lot_size']

        lott = partial_lot_size + lot_size
        lott = round(lott, 2)

   
        if not mt5.initialize(path=f"C:/Program Files/MetaTrader 5_{account}/terminal64.exe",
                            login=login, server=server, password=password):
            logger.info("initialize() failed, error code =")
            return

        if not mt5.login(login, password, server):
            logger.info("Login failed")
            return
        
        while True:
            try:
                time.sleep(0.5)
                with open("pairs_logic.json", "r") as file:
                    inputs = json.load(file)

                tp_mapping = inputs['pairs_tp_mapping_real']
                sl_mapping = inputs['pairs_stoploss_mapping_real']

                sl_mapping_inputted = inputs["pairs_stoploss_mapping_input"] 
                interval_of_pair = inputs['pairs_interval_mapping']
                partial_sl_points = inputs['sl_for_partial_lot']
                ctc_input = inputs['pairs_ctc_mapping']

                inter = str(interval_of_pair[f'{SYMBOL_REAL}']) + "m"

                positions = mt5.positions_get()
                df = get_forex_history(pair=symbol, interval= inter)
                candle_dt = df.iloc[-1]
                signal_candle_high = candle_dt['high']
                signal_candle_low = candle_dt['low']
                signal_candle_close = candle_dt['close']

                for pos in positions:
                    if pos.comment == "second leg":
                        break

                    symbol_ = pos.symbol

                    if symbol_ != symbol:
                        continue
                    symbol = pos.symbol

                    order_type = pos.type 
                    tick = mt5.symbol_info_tick(symbol)
                    bid = tick.bid
                    ask = tick.ask
                    mt5_entry_price = pos.price_open
                    volume = pos.volume


                
                    if order_type == mt5.ORDER_TYPE_BUY:
                        side = "buy"
                    elif order_type == mt5.ORDER_TYPE_SELL:
                        side = "sell"
                        

                    pips_to_points = 1
        
                    tp_point = tp_mapping[symbol] * pips_to_points
                    sl_point = sl_mapping[symbol] * pips_to_points

                    with lock_entry_prices:
                        with open("entry_prices_tv.json", "r") as e_p:
                            dttt = json.load(e_p)

                    entry_price = dttt[symbol]
                    print(f"entry price is: {entry_price}")

    
                    if side == "buy":
                        print(f"sl point: {sl_point}, tp point: {tp_point}")
                        real_tp_lev = entry_price + tp_point
                        real_sl_lev = mt5_entry_price - sl_point
                        partial_sl_lev = mt5_entry_price - partial_sl_points

                        print(f"real tp of: {symbol} is-- {real_tp_lev}")
                        print(f"real sl of: {symbol} is-- {real_sl_lev}")
                        print(f"partial sl of: {symbol} is-- {partial_sl_lev}")


                        if signal_candle_high >= real_tp_lev:
                            print("tp")
                            close_positions_of_this_pair(symbol=symbol)

                        if signal_candle_close <= partial_sl_lev and volume == lott:
                            print("partial")
                            close_positions_of_this_pair(symbol=symbol, partial_close=True)

                        if signal_candle_close <= real_sl_lev:
                            print("sl")
                            close_positions_of_this_pair(symbol=symbol)


                    if side == "sell":
                        real_tp_lev = entry_price - tp_point
                        real_sl_lev = mt5_entry_price + sl_point
                        partial_sl_lev = mt5_entry_price + partial_sl_points
           

                        print(f"real tp of: {symbol} is-- {real_tp_lev}")
                        print(f"real sl of: {symbol} is-- {real_sl_lev}")
                        print(f"partial sl of: {symbol} is-- {partial_sl_lev}")

                        if signal_candle_low <= real_tp_lev:
                            print("tp")
                            close_positions_of_this_pair(symbol=symbol)


                        if signal_candle_close >= partial_sl_lev  and volume == lott:
                            print("partial")
                            close_positions_of_this_pair(symbol=symbol, partial_close=True)


                        if signal_candle_close >= real_sl_lev:
                            print("sl")
                            close_positions_of_this_pair(symbol=symbol)


                now_time = datetime.now().time().replace(second=0, microsecond=0)
                inteval = extract_news_interval(fetch_news=False)

                if not inteval:
                    logger.info("no news today..") 

                else:
                    logger.info("news present today!")

                for i in inteval:
                    before_str = i['before']
                    before = datetime.strptime(before_str, "%H:%M").time()
                    before_dt = datetime.combine(date.today(), before)
                    before_dt = before_dt - timedelta(minutes=2)
                    before_time_new = before_dt.time()


                    if now_time > before_time_new and now_time < before:
                        logger.info("closing this positon because news period going to come~")
                        close_positions_of_this_pair(symbol=symbol, cut_riverse=True)


            except Exception as e:
                logger.info(f"Error in side sl_tp manager for all pairs!: {e}")

                if not mt5.initialize(path=f"C:/Program Files/MetaTrader 5_{account}/terminal64.exe",
                                    login=login, server=server, password=password):
                    logger.info("initialize() failed, error code =")


                if not mt5.login(login, password, server):
                    logger.info("Login failed")


    



def logic_processing_here(symbol, trade_side):
    time.sleep(5)
    symbol = SYMBOL_REAL


    logger.info(f"logic procesing is started for: {symbol}")

    with open("pairs_logic.json", "r") as file:
        inputs = json.load(file)

    sl_mapping_inputted = inputs["pairs_stoploss_mapping_input"]
    inputs['pairs_stoploss_mapping_real'][symbol] = sl_mapping_inputted[symbol]

    with open("pairs_logic.json", "w") as file:
        json.dump(inputs, file, indent=4)


    trade_side = trade_side.lower()
    pips_to_points = 1

    with open("pairs_logic.json", "r") as file:
        inputs = json.load(file)


    buffer_mapping = inputs['pairs_buffer_mapping']
    distance_mapping = inputs['pairs_distance_mapping']
    stoploss_mapping = inputs['pairs_stoploss_mapping']
    ctc_mapping = inputs['pairs_ctc_mapping']
    tp_mapping = inputs['pairs_tp_mapping']
    candle_distance_mapping = inputs['pairs_candle_distance_mapping']
    interval_of_pair = inputs['pairs_interval_mapping']



    inter = str(interval_of_pair[f'{symbol}']) + "m"
    df = get_forex_history(pair=symbol, interval= inter)

    candle_dt = df.iloc[-2]

    signal_candle_close = candle_dt['close']
    signal_candle_high = candle_dt['high']
    signal_candle_low = candle_dt['low']
    signal_candle_open = candle_dt['open']


    buffer = buffer_mapping[symbol]
    buffer = buffer * pips_to_points

    distance = distance_mapping[symbol]
    distance = distance * pips_to_points

    stop_loss = stoploss_mapping[symbol]
    stop_loss = stop_loss * pips_to_points

    ctc = ctc_mapping[symbol]
    ctc = ctc * pips_to_points

    tp = tp_mapping[symbol]
    tp = tp * pips_to_points

    candle_distance = candle_distance_mapping[symbol]
    candle_distance = candle_distance  * pips_to_points

    interval = interval_of_pair[symbol]

    for k, v in {
        "Buffer": buffer,
        "Distance": distance,
        "Stop Loss": stop_loss,
        "CTC": ctc,
        "TP": tp,
        "Candle Distance": candle_distance,
        "interval": interval
    }.items():
        logger.info(f"{k} is: {v}")


    if trade_side == "buy":
        buffer_level = signal_candle_close + buffer

    else:
        buffer_level = signal_candle_close - buffer


    l = 0
    fake_signal_level = 0
    execute_trade_level = 0


    while True:
        try:
            with lock_pairs_signal:
                with open("pairs_signal.json", "r") as ps:
                    signal_store = json.load(ps)

                signal_store_dt = signal_store[symbol]

                if signal_store_dt != trade_side:
                    logger.info(f"signal changed to:{trade_side} to {signal_store_dt} closing the thread~")
                    sys.exit()


            diff_seconds, multiplier = seconds_to_next_interval(interval)
            time.sleep(diff_seconds)

            for i in range(6):
                time.sleep(1)

                with lock_pairs_signal:
                    with open("pairs_signal.json", "r") as ps:
                        signal_store = json.load(ps)

                    signal_store_dt = signal_store[symbol]

                    if signal_store_dt != trade_side:
                        logger.info(f"signal changed to:{trade_side} to {signal_store_dt} closing the thread~")
                        sys.exit()


            df = get_forex_history(pair=symbol, interval= inter)
            candle_dt = df.iloc[-2]

            high = candle_dt['high']
            low = candle_dt['low']
            close = candle_dt['close']
            openn = candle_dt['open']

            with open("candles_store.json", "r") as candle_file:
                candle_info = json.load(candle_file)

            try:
                tick = candle_info['candle']
                high_pre = tick['high']
                low_pre = tick['low']
                close_pre = tick['close']
                open_pre = tick['open']


                if high == high_pre and close == close_pre:
                    logger.info("candle data didnt recived latest")
                    time.sleep(10)
                    df = get_forex_history(pair=symbol, interval= inter) 
                    if df is None or df.empty:
                        df = get_forex_history(pair=symbol, interval= inter) 

                    candle_dt = df.iloc[-2]
                    high_now = candle_dt['high']
                    low_now = candle_dt['low']
                    close_now = candle_dt['close']
                    openn_now = candle_dt['open']

                    if high_now == high_pre and close == close_pre:
                        logger.info("again didnt get latest tick data")
                        df = get_forex_history(pair=symbol, interval= inter) 
                        candle_dt = df.iloc[-2]

                        high = candle_dt['high']
                        low = candle_dt['low']
                        close = candle_dt['close']
                        openn = candle_dt['open']
                    
                    else:
                        logger.info("now got correct tick data!!")
                        candle_dt = df.iloc[-2]
                        high = candle_dt['high']
                        low = candle_dt['low']
                        close = candle_dt['close']
                        openn = candle_dt['open']

            except Exception as e:
                logger.info(f"candle store file has some issues: {e}")

            data = {"candle": {"open": openn, "high": high, "low": low, "close": close}}

            with open("candles_store.json", "w") as candle_file:
                json.dump(data, candle_file, indent=4)


            logger.info(f"high: {high}, low: {low}, close: {close}, openn: {openn}")
            logger.info(f"buffer level: {buffer_level}")


            if trade_side == "buy":
                if high >= buffer_level and l == 0:
                    logger.info(f"buffer touched or breaked for: {symbol}")
                    l += 1

                    cd = high - low
                    overall_distance = high - signal_candle_low


                    if overall_distance < distance:
                        logger.info(f"overall distance logic passed! for: {symbol}")
                    
                    else:
                        logger.info(f"overall distance is greater then required! for: {symbol}")
                        break

                    if cd < candle_distance:
                        logger.info(f"candle distance logic passed! for: {symbol}")
                    
                    else:
                        logger.info(f"candle distance {cd} is greater then {candle_distance} required! for: {symbol}")
                        break



                elif l == 1 and close > openn:
                    logger.info(f"green candle formed for: {symbol}")
                    l += 1

                    cd = high - low

                    if cd < candle_distance:
                        logger.info(f"candle distance logic passed! for: {symbol}")
                    
                    else:
                        logger.info(f"candle distance {cd} is greater then {candle_distance} required! for: {symbol}")
                        break

                    logger.info(f"execute trade for buy side for: {symbol}")
                    wait_if_between_news_period(fetch_news=True)
                    with lock_entry_prices:
                        with open("entry_prices_tv.json", "r") as e_p:
                            dttt = json.load(e_p)

                        dttt[symbol] = close

                        with open("entry_prices_tv.json", "w") as ep:
                            json.dump(dttt, ep, indent=4)
                        time.sleep(3)
                    execute_on_exness_mt5(symbol=symbol ,side="buy", sl=stop_loss, tp=tp)

                    l += 1

                

                elif l == 1 and close < openn:
                    logger.info(f"red candle formed for: {symbol}")
                    fake_signal_level = openn - buffer
                    execute_trade_level = openn + (buffer / 2)
                    l += 1

                    logger.info(f"fake signal level for: {symbol} is {fake_signal_level}")
                    logger.info(f"execute trade level for: {symbol} is {execute_trade_level}")


                
                elif l == 2:
                    if close < fake_signal_level:
                        logger.info("signal is cancelled candle closed below fakeout threshold")
                        break

                    
                    elif close > execute_trade_level:
                        cd = high - low

                        if cd < candle_distance:
                            logger.info(f"candle distance logic passed! for: {symbol}")
                        
                        else:
                            logger.info(f"candle distance {cd} is greater then {candle_distance} required! for: {symbol}")
                            break


                        logger.info(f"execute trade for buy side for: {symbol}")
                        wait_if_between_news_period(fetch_news=True)
                        with lock_entry_prices:
                            with open("entry_prices_tv.json", "r") as e_p:
                                dttt = json.load(e_p)

                            dttt[symbol] = close

                            with open("entry_prices_tv.json", "w") as ep:
                                json.dump(dttt, ep, indent=4)
                            time.sleep(3)
                        execute_on_exness_mt5(symbol=symbol ,side="buy", sl=stop_loss, tp=tp)

                        l += 1


                elif l == 3:
                    candle_color = "green" if openn <= close else "red"

                    if candle_color == "red":
                        logger.info(f"riverse red candle form waiting for another one in!: {symbol}")
                        l += 1

                    else:
                        print(f"No riverse candle logic formed for: {symbol}")
                        break


                elif l == 4:
                    candle_color = "green" if openn <= close else "red"

                    if candle_color == "red":
                        logger.info(f"riverse logic formed closing the trade..")
                        close_positions_of_this_pair(symbol=symbol)
                        break
                    
                    else:
                        print(f"No riverse candle logic formed for: {symbol}")
                        break

 
                else:
                    cd = high - low
                    overall_distance = high - signal_candle_low

                    logger.info(f"candle distance is: {cd}, overall_distance is: {overall_distance}, logic number: {l}")
 



            else:
                logger.info(f"processing sell signal inside else: logic number {l}")
                if low <= buffer_level and l == 0:
                    logger.info(f"buffer touched or breaked for: {symbol}")
                    l += 1
                    overall_distance =  signal_candle_high - low
                    cd = high - low

                    if overall_distance < distance:
                        logger.info(f"overall distance logic passed! for: {symbol}")
                    
                    else:
                        logger.info(f"candle distance {cd} is greater then {candle_distance} required! for: {symbol}")
                        break


                    if cd < candle_distance:
                        logger.info(f"candle distance logic passed! for: {symbol}")
                    
                    else:
                        logger.info(f"candle distance {cd} is greater then {candle_distance} required! for: {symbol}")
                        break

                    
                elif l == 1 and close < openn:
                    logger.info(f"red candle formed for: {symbol}")
                    l += 1
                    cd = high - low

                    if cd < candle_distance:
                        logger.info(f"candle distance logic passed! for: {symbol}")
                    
                    else:
                        logger.info(f"candle distance {cd} is greater then {candle_distance} required! for: {symbol}")
                        break
                    

                    logger.info(f"execute trade for: {symbol}")
                    wait_if_between_news_period(fetch_news=True)
                    with lock_entry_prices:
                        with open("entry_prices_tv.json", "r") as e_p:
                            dttt = json.load(e_p)

                        dttt[symbol] = close

                        with open("entry_prices_tv.json", "w") as ep:
                            json.dump(dttt, ep, indent=4)
                        time.sleep(3)
                    execute_on_exness_mt5(symbol=symbol ,side="sell", sl=stop_loss, tp=tp)

                    l += 1



                elif l == 1 and close > openn:
                    logger.info(f"green candle formed for: {symbol}")
                    fake_signal_level = openn + buffer
                    execute_trade_level = openn - (buffer / 2)
                    l += 1

                    logger.info(f"fake signal level for: {symbol} is {fake_signal_level}")
                    logger.info(f"execute trade level for: {symbol} is {execute_trade_level}")


                
                elif l == 2:
                    if close > fake_signal_level:
                        logger.info("signal is cancelled candle closed upward fakeout threshold")
                        break

                    
                    elif close < execute_trade_level:
                        cd = high - low

                        if cd < candle_distance:
                            logger.info(f"candle distance logic passed! for: {symbol}")
                        
                        else:
                            logger.info(f"candle distance {cd} is greater then {candle_distance} required! for: {symbol}")
                            break


                        logger.info(f"execute trade for sell side for: {symbol}")
                        wait_if_between_news_period(fetch_news=True)
                        with lock_entry_prices:
                            with open("entry_prices_tv.json", "r") as e_p:
                                dttt = json.load(e_p)

                            dttt[symbol] = close

                            with open("entry_prices_tv.json", "w") as ep:
                                json.dump(dttt, ep, indent=4)
                            time.sleep(3)
                        execute_on_exness_mt5(symbol=symbol, side="sell", sl=stop_loss, tp=tp)
                        l += 1


                elif l == 3:
                    candle_color = "green" if openn <= close else "red"

                    if candle_color == "green":
                        logger.info(f"riverse red candle form waiting for another one in!: {symbol}")
                        l += 1

                    else:
                        print(f"No riverse candle logic formed for: {symbol}")
                        break


                elif l == 4:
                    candle_color = "green" if openn <= close else "red"

                    if candle_color == "green":
                        logger.info(f"riverse logic formed closing the trade.. for: {symbol}")
                        close_positions_of_this_pair(symbol=symbol)
                        break
                        
                    else:
                        print(f"No riverse candle logic formed for: {symbol}")
                        break


                else:
                    overall_distance =  signal_candle_high - low
                    cd = high - low

                    logger.info(f"candle distance is: {cd}, overall_distance is: {overall_distance}, logic number: {l}")
 

        except Exception as e:
            logger.info(f"error inside loggic processing function: {e}")




def running_pos_lot_size():
    with open("cred.json", 'r') as file:
        cred = json.load(file)

    cred = cred['user1']
    login = cred['account_number']
    server = cred['server']
    password = cred['password']
    account = cred['account']
 

    if not mt5.initialize(path=f"C:/Program Files/MetaTrader 5_{account}/terminal64.exe",login=login, server=server,password=password):
        print("at line 1609")
        print("initialize() failed, error code =",mt5.last_error())
        return None
    
    authorized = mt5.login(login, password, server)
    if authorized:
        position = mt5.positions_get()

    total_lot_size = sum(pos.volume for pos in position)
    return total_lot_size



def running_pos_trade_side_comm():
    try:
        with open("cred.json", 'r') as file:
            cred = json.load(file)

        cred = cred['user1']
        login = cred['account_number']
        server = cred['server']
        password = cred['password']
        account = cred['account']
    

        if not mt5.initialize(path=f"C:/Program Files/MetaTrader 5_{account}/terminal64.exe",login=login, server=server,password=password):
            print("at line 1609")
            print("initialize() failed, error code =",mt5.last_error())
            return None
        
        authorized = mt5.login(login, password, server)
        side, comment = 0,0

        if authorized:
            position = mt5.positions_get()
            for pos in position:
                if pos.type == mt5.ORDER_TYPE_BUY:
                    side = "BUY"
                elif pos.type == mt5.ORDER_TYPE_SELL:
                    side = "SELL"

                comment = pos.comment

            return side, comment
    
    except Exception as e:
        logger.info(f"Error inside running pos trade side and comment func: {e}")







def get_forex_history(pair: str, interval= "1h"):
    with open("cred.json", 'r') as file:
        cred = json.load(file)

    cred = cred['user1']
    login = cred['account_number']
    server = cred['server']
    password = cred['password']
    account = cred['account']
 

    if not mt5.initialize(path=f"C:/Program Files/MetaTrader 5_{account}/terminal64.exe",login=login, server=server,password=password):
        print("at line 1609")
        print("initialize() failed, error code =",mt5.last_error())
        return None
    timezone = pytz.timezone("Etc/UTC")

    if interval == "30m":
        interval = mt5.TIMEFRAME_M30
    elif interval == "15m":
        interval = mt5.TIMEFRAME_M15
    elif interval == "1m":
        interval = mt5.TIMEFRAME_M1


    rates = mt5.copy_rates_from_pos(pair, interval, 0, 200)
    if rates is None:
        return None

    rates = pd.DataFrame(rates)
    rates['time']=pd.to_datetime(rates['time'], unit='s')

    candle_stick = rates.iloc[-200:]
    candle_stick = rates.drop(["time", "real_volume", "spread" , "tick_volume"], axis = 1)

    return candle_stick





def seconds_to_next_interval(interval_minutes=30):
    now = datetime.now()
    minutes = now.minute
    seconds = now.second

    # Calculate next interval mark (e.g., every 15 or 30 mins)
    next_interval = ((minutes // interval_minutes) + 1) * interval_minutes
    multiplier = minutes // interval_minutes  # which block we are in (0,1,2...)

    # Handle wrap-around at hour end
    if next_interval >= 60:
        next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_time = now.replace(minute=next_interval, second=0, microsecond=0)

    diff_seconds = int((next_time - now).total_seconds())

    return diff_seconds, multiplier



if __name__ == "__main__":
    riverse_trade_master()