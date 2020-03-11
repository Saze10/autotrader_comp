import asyncio
from typing import List, Tuple
from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side
import time
import itertools

class AutoTrader(BaseAutoTrader):
    
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        
        # History for each instrument - contains a key for average ask/bid prices and a key for the actual history list
        self.etf_history = {"average": {"ask":0, "bid":0}, "history":[]}
    
        self.future_history = {"average": {"ask":0, "bid":0}, "history":[]}
        self.op_history = []
        
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0
        self.trade_tick_list = [] # History of trade ticks
        self.total_fees = 0.0 # Total fees collected
        self.order_ids = itertools.count(1)

        self.active_order_history = {}

        self.base_time = time.time()

        self.previous_sells = [0] * 10

        self.previous_buys = [0] * 10
        
    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.
        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        self.on_order_status_message(client_order_id, 0, 0, 0)
        self.op_send_cancel_order(client_order_id)
        
    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.
        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        # Update operation history for past second
        self.update_op_history()
        # Entry containing ask and bid prices for given instrument
        new_entry = {
            "ask": 0,
            "bid": 0
        }
        
        # Entries containing volume and price for given ask/bid
        new_ask_data = {
            "volume": [],
            "price": ask_prices[0]
        }
        for v in ask_volumes:
            new_ask_data["volume"].append(v)
        
        new_bid_data = {
            "volume": [],
            "price": bid_prices[0]
        }
        for v in bid_volumes:
            new_bid_data["volume"].append(v)
            
        # Append data to corresponding list within entry dictionary
        new_entry["ask"] = new_ask_data
        new_entry["bid"] = new_bid_data
        
        if instrument == Instrument.ETF:
            self.etf_history["history"].append(new_entry)
            if len(self.etf_history["history"]) > 150:
                del self.etf_history["history"][0]
            self.update_average(self.etf_history)
        elif instrument == Instrument.FUTURE:
            self.future_history["history"].append(new_entry)
            if len(self.future_history["history"]) > 150:
                del self.future_history["history"][0]
            self.update_average(self.future_history)

        """
        self.logger.warning("FUTURE HISTORY AVERAGE ASK IS: %d", int(self.future_history["average"]["ask"]))
        self.logger.warning("FUTURE HISTORY AVERAGE BID IS: %d", int(self.future_history["average"]["bid"]))
        self.logger.warning("ETF HISTORY AVERAGE ASK IS %d", int(self.etf_history["average"]["ask"]))
        self.logger.warning("ETF HISTORY AVERAGE BID IS %d", int(self.etf_history["average"]["bid"]))

        self.logger.warning("Current future dictionary length: %d", len(self.future_history["history"]))
        self.logger.warning("Current ETF dictionary length: %d", len(self.etf_history["history"]))
        self.logger.warning("Boolean Value of if statement: %d", int(len(self.future_history["history"]) < 100 or len(self.etf_history["history"]) < 100))
        """

        self.logger.warning("Below is the active order history:")
        self.logger.warning(str(self.active_order_history))
                
        def order_quantity(trader_stance):
            """trader_stance is a boolean: True = passive, False = aggressive"""
            if trader_stance == True:
                return int(min(sum(bid_volumes), sum(ask_volumes)) * 0.5 * (sum(self.trade_tick_list[len(self.trade_tick_list)-3 : len(self.trade_tick_list)-1]) + """need to add our volume""" )) 
            else:
                return int(abs(sum(bid_volumes)-sum(ask_volumes)) * 0.5 * (sum(self.trade_tick_list[len(self.trade_tick_list)-3 : len(self.trade_tick_list)-1]) + """need to add our volume""" ))


        def get_net_threshold(period):
            if len(self.trade_tick_list) > 0:
                volume_sum = 0
                if period > len(self.trade_tick_list):
                    period = len(self.trade_tick_list)
                    
                for i in range(period):
                    volume_sum += sum(self.trade_tick_list[i])[1]/len(self.trade_tick_list[i])
                
                volume_sum /= period
                return volume_sum

        if (ask_volumes[0] != 0 and bid_volumes[0] != 0 and len(self.trade_tick_list) > 0):
            volume_difference = abs(sum(bid_volumes) - sum(ask_volumes))/(sum(bid_volumes) + sum(ask_volumes)) # When this is greater than 0.5 adopt aggressive trend-following strategy, otherwise passive based on last trade

            last_trading_price = self.trade_tick_list[len(self.trade_tick_list)-1]
            ask_bid_spread = ask_prices[0] - bid_prices[0]

            if volume_difference > 0.5: # Aggressive strategy                
                if self.position > 75 or self.position < -75:
                    # Make an ask at the last trading price + ask_bid_spread
                    ask_trading_price = self.round_to_trade_tick(last_trading_price[len(last_trading_price)-1][0] + ask_bid_spread)
                    
                    self.ask_id = next(self.order_ids)
                    self.op_send_insert_order(self.ask_id, Side.SELL, ask_trading_price, 1, Lifespan.FILL_AND_KILL)

                    # Make a bid at last trade price
                    bid_trading_price = self.round_to_trade_tick(last_trading_price[0][0])
                    
                    self.bid_id = next(self.order_ids)
                    self.op_send_insert_order(self.bid_id, Side.BUY, bid_trading_price, 1, Lifespan.FILL_AND_KILL)

                else: 
                    # Make an ask at the last trading price
                    ask_trading_price = self.round_to_trade_tick(last_trading_price[len(last_trading_price)-1][0])
                    
                    self.ask_id = next(self.order_ids)
                    self.op_send_insert_order(self.ask_id, Side.SELL, ask_trading_price, 1, Lifespan.FILL_AND_KILL)

                    # Make a bid at last trade price - ask bid spread
                    bid_trading_price = self.round_to_trade_tick(last_trading_price[0][0] - ask_bid_spread)
                    
                    self.bid_id = next(self.order_ids)
                    self.op_send_insert_order(self.bid_id, Side.BUY, bid_trading_price, 1, Lifespan.FILL_AND_KILL)

            else: # Passive strategy
                ask_trading_price = self.round_to_trade_tick(last_trading_price[len(last_trading_price)-1][0] + 0.5 * ask_bid_spread)
                bid_trading_price = self.round_to_trade_tick(last_trading_price[0][0] - 0.5 * ask_bid_spread)

                #TESTING GFD VS FAK TRADES
#####################################
                self.bid_id = next(self.order_ids)
                self.op_send_insert_order(self.bid_id, Side.BUY, bid_trading_price, 1, Lifespan.GOOD_FOR_DAY)
                self.ask_id = next(self.order_ids)
                self.op_send_insert_order(self.ask_id, Side.SELL, ask_trading_price, 1, Lifespan.GOOD_FOR_DAY)
######################################

                    
    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes.
        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.
        If an order is cancelled its remaining volume will be zero.
        """
        # Update operation history for past second
        self.update_op_history()

        if remaining_volume == 0 and client_order_id in self.active_order_history.keys():
            del self.active_order_history[client_order_id]

        self.total_fees += fees

        self.logger.warning("Total fees: %f", self.total_fees)

        """
        if remaining_volume != 0:
            if self.op_count < 20:
                self.send_amend_order(client_order_id, int(remaining_volume * 1.1))
                #dont know what the third parameter for the above should be. Need concrete position information to implement this properly 
                self.op_count += 1
        """
        
    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes.
        Since every trade in the ETF is automatically hedged in the future,
        future_position and etf_position will always be the inverse of each
        other (i.e. future_position == -1 * etf_position).
        """
        self.logger.warning("Our position is: %d", self.position)
        self.position = etf_position
        
    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.
        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        self.trade_tick_list.append(trade_ticks)

        for key in list(self.active_order_history.keys()):
            temp = list(self.active_order_history[key]) # Convert tuple to list
            temp[1] += 1
            self.active_order_history[key] = tuple(temp)
            if self.active_order_history[key][1] > 3:
                if self.op_send_cancel_order(key): # This function returns true if cancel is successful
                    del self.active_order_history[key]
            
                
        
    def collapse_history(self, history): # Run only if history entries are greater than or equal to 202 - accounting for the two
        if(len(history["history"]) >= 200): # Making sure we avoid key errors
            self.logger.warning("I'm collapsing the history lolol")
            avg_entry = {
            "ask": 0,
            "bid": 0
            }
            
            # Loop through the history's entries
            for i in range(100):
                avg_entry["ask"] += history["history"][i]["ask"]["price"]
                avg_entry["bid"] += history["history"][i]["bid"]["price"]
                
            # Get the average
            avg_entry["ask"] /= 101
            avg_entry["bid"] /= 101
            for i in range(100):
                del history["history"][0]
            # Update the average dictionary entry
            history["average"] = avg_entry

    def update_average(self, history):
        depth = 0
        
        if len(history["history"]) < 100:
            depth = len(history["history"])
        else:
            depth = 100
        
        avg_ask = 0
        avg_bid = 0
        
        for i in range(depth):
            avg_ask += history["history"][len(history["history"]) - 1 - i]["ask"]["price"]
            avg_bid += history["history"][len(history["history"]) - 1 - i]["bid"]["price"]
        
        avg_ask /= depth
        avg_bid /= depth

        history["average"]["ask"] = avg_ask
        history["average"]["bid"] = avg_bid
            
    # Helper functions for checking breaches
    def op_send_insert_order(self, client_order_id: int, side: Side, price: int, volume: int, lifespan: Lifespan) -> None:
        if self.get_projected_op_rate(1) <= 19.5: # Technically should be 20 - setting it stricter for now
            if (side == Side.BUY and self.position < 100) or (side == Side.SELL and self.position > -100):
                self.send_insert_order(client_order_id, side, price, volume, lifespan)
                self.op_history.append(time.time())
                if lifespan == Lifespan.GOOD_FOR_DAY:
                    self.active_order_history[client_order_id] = (client_order_id, 0)

    def op_send_cancel_order(self, client_order_id: int) -> None:
        if self.get_projected_op_rate(1) <= 19.5: # Technically should be 20 - setting it stricter for now
            self.send_cancel_order(client_order_id)
            self.op_history.append(time.time())
            return True
        return False

    def op_send_amend_order(self, client_order_id: int, volume: int) -> None:
        if self.get_projected_op_rate(1) <= 19.5: # Technically should be 20 - setting it stricter for now
            self.send_amend_order(client_order_id, volume)
            self.op_history.append(time.time())
        
    def update_op_history(self):
        counter = 0
        for entry in self.op_history:
            if time.time() - entry >= 1.1:
                counter += 1
            else:
                break
        for i in range(counter):
            del self.op_history[0]
        
    def get_projected_op_rate(self, num_ops): # Second parameter is the number of ops to be taken
        if len(self.op_history) > 0:
            return (len(self.op_history)+num_ops)/(time.time() - self.op_history[0])
        else: # If list is empty we can probably do a safe insert since op history has the operations from the past second
            return 0

    def round_to_trade_tick(self, integer):
        return int(integer/100) * 100
        
