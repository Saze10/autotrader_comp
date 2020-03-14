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

        self.predicted_hedge_price = 0
        
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0
        self.trade_tick_list = [] # History of trade ticks
        self.total_fees = 0.0 # Total fees collected
        self.order_ids = itertools.count(1)

        self.active_order_history = {}

        self.base_time = time.time()

        self.previous_sells = [0] * 10

        self.previous_buys = [0] * 10

        self.number_of_matches_in_tick = 0
        
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

        self.logger.warning("Below is the active order history:")
        self.logger.warning(str(self.active_order_history))


        def check_active_order_position():
            sum_positive = 0
            sum_negative = 0
            for key in list(self.active_order_history.keys()):
                if self.active_order_history[key][4] == Side.BUY:
                    sum_positive += self.active_order_history[key][3]
                else:
                    sum_negative -= self.active_order_history[key][3]
            self.logger.warning("active order position: %d", sum_positive + sum_negative + self.position)
            self.logger.warning("sum_positive: %d, sum_negative: %d", sum_positive, sum_negative)
            return (self.position + sum_positive, self.position + sum_negative)
 
        def order_quantity(trader_stance, side):
            """trader_stance is a boolean: True = passive, False = aggressive. 
            side is order side (buy or sell). True = buy, False = sell"""
            
            if trader_stance:
                volume = int(min(sum(bid_volumes),sum(ask_volumes))/10000 * 0.5 * (self.number_of_matches_in_tick))
                
                #checking for cumulative position of active orders + current volume
                active_order_position = check_active_order_position()
                
                if active_order_position[0] + volume >= 90 and side:
                    self.logger.warning("order_quantity returns+: %d", 90 - active_order_position[0])
                    return 90 - active_order_position[0]
                elif active_order_position[1] - volume <= -90 and not side:
                    self.logger.warning("order_quantity returns -: %d", 90 + active_order_position[1])
                    return 90 + active_order_position[1]
                else:
                    self.logger.warning("order_quantity returns +-: %d", volume)
                    return volume


            else:
                volume = int((abs(sum(bid_volumes)-sum(ask_volumes))/10000) * 0.5 * (self.number_of_matches_in_tick))

                active_order_position = check_active_order_position()
                
                if active_order_position[0] + volume >= 90 and side:
                    self.logger.warning("order_quantity returns +: %d", 90 - active_order_position[0])
                    return 90 - active_order_position[0]
                elif active_order_position[1] - volume <= -90 and not side:
                    self.logger.warning("order_quantity returns -: %d", 90 + active_order_position[1])
                    return 90 + active_order_position[1]
                else:
                    self.logger.warning("order_quantity returns +-: %d", volume)
                    return volume

        # Amon's layout is 0: id  1: tick number 2: side 3: price 4: volume
        # Andrew's layout is 0: id  1: tick number 2: price 3: volume 4: side
        # Change amon's things to the equivalent in andrew - should be done now
        def check_same_price_order(side, trading_price, order_id, trading_volume):
            self.logger.warning("Checking for same price")
            
            for key in list(self.active_order_history.keys()):
                if self.active_order_history[key][4] != side and self.active_order_history[key][2] == trading_price:
                    self.op_send_cancel_order(self.active_order_history[key][0])
                    self.op_send_insert_order(order_id, side, trading_price, trading_volume, Lifespan.GOOD_FOR_DAY)
                    return True
                elif self.active_order_history[key][4] == side and self.active_order_history[key][2] == trading_price:
                    return True

            return False

        def suicide_intervention():
            for key in list(self.active_order_history.keys()):
                if self.active_order_history[key][4] == Side.BUY:
                    if self.position + self.active_order_history[key][3] > 90:
                        self.logger.warning("Please call suicide hotline at 13 11 14.")
                        new_volume = abs(90 - self.position)
                        if new_volume > 0:
                            if new_volume != self.active_order_history[key][3]: 
                                self.op_send_amend_order(key, new_volume)
                        else:
                            self.op_send_cancel_order(key)
                else: # Sell case
                    if self.position - self.active_order_history[key][3] < -90:
                        self.logger.warning("Please call suicide hotline at 13 11 14.")
                        new_volume = abs(- self.position - 90)
                        if new_volume > 0:
                            if new_volume != self.active_order_history[key][3]: 
                                self.op_send_amend_order(key, new_volume)
                        else:
                            self.op_send_cancel_order(key)
                            

        suicide_intervention()
        
        # BEAR ENGINE
        if len(bid_prices) > 0 and len(ask_prices) > 0:
            if instrument == Instrument.FUTURE:
                self.predicted_hedge_price = (bid_prices[0] + ask_prices[0])/2
            elif instrument == Instrument.ETF and self.predicted_hedge_price > 0:
                for i in range(len(bid_prices)):
                    if self.position <= 0:
                        if self.predicted_hedge_price > bid_prices[i]:
                            active_order_position = check_active_order_position()
                            new_bid_volume = bid_volumes[i]

                            self.logger.warning("Considering bid volume %d", new_bid_volume)
                    
                            if active_order_position[0] + new_bid_volume > 90:
                                new_bid_volume = 90 - active_order_position[0]
                                self.logger.warning("new_bid_volume returns +: %d", 90 - active_order_position[0])
                                
                            if new_bid_volume > 0:
                                
                                if new_bid_volume > 20: # For safety
                                    new_bid_volume = 20
                                
                                self.bid_id = next(self.order_ids)
                                self.op_send_insert_order(self.bid_id, Side.BUY, bid_prices[i], new_bid_volume, Lifespan.GOOD_FOR_DAY)
                            
                        if self.predicted_hedge_price < ask_prices[i]:
                            active_order_position = check_active_order_position()
                            new_ask_volume = ask_volumes[i]

                            self.logger.warning("Considering ask volume %d", new_ask_volume)
                    
                            if active_order_position[1] - new_ask_volume < -90:
                                new_ask_volume = 90 + active_order_position[1]
                                self.logger.warning("new_ask_volume returns -: %d", 90 + active_order_position[1])

                            if new_ask_volume > 0:
                                if new_ask_volume > 20: # For safety
                                    new_ask_volume = 20
                                self.ask_id = next(self.order_ids)
                                self.op_send_insert_order(self.ask_id, Side.SELL, ask_prices[i], new_ask_volume, Lifespan.GOOD_FOR_DAY)
                    else: # Literally the above code reversed in order
                        if self.predicted_hedge_price < ask_prices[i]:
                            active_order_position = check_active_order_position()
                            new_ask_volume = ask_volumes[i]

                            self.logger.warning("Considering ask volume %d", new_ask_volume)
                    
                            if active_order_position[1] - new_ask_volume < -90:
                                new_ask_volume = 90 + active_order_position[1]
                                self.logger.warning("new_ask_volume returns -: %d", 90 + active_order_position[1])

                            if new_ask_volume > 0:
                                if new_ask_volume > 20: # For safety
                                    new_ask_volume = 20
                                self.ask_id = next(self.order_ids)
                                self.op_send_insert_order(self.ask_id, Side.SELL, ask_prices[i], new_ask_volume, Lifespan.GOOD_FOR_DAY)
                                
                        if self.predicted_hedge_price > bid_prices[i]:
                            active_order_position = check_active_order_position()
                            new_bid_volume = bid_volumes[i]

                            self.logger.warning("Considering bid volume %d", new_bid_volume)
                    
                            if active_order_position[0] + new_bid_volume > 90:
                                new_bid_volume = 90 - active_order_position[0]
                                self.logger.warning("new_bid_volume returns +: %d", 90 - active_order_position[0])
                                
                            if new_bid_volume > 0:
                                if new_bid_volume > 20: # For safety
                                    new_bid_volume = 20
                                
                                self.bid_id = next(self.order_ids)
                                self.op_send_insert_order(self.bid_id, Side.BUY, bid_prices[i], new_bid_volume, Lifespan.GOOD_FOR_DAY)
        
        suicide_intervention()

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

        if remaining_volume > 0 and fill_volume > 0 and client_order_id in self.active_order_history.keys():
            temp = list(self.active_order_history[client_order_id]) # Convert tuple to list
            temp[1] = 0
            self.active_order_history[client_order_id] = tuple(temp)
            

        if remaining_volume == 0 and client_order_id in self.active_order_history.keys():
            del self.active_order_history[client_order_id]


        
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
        self.number_of_matches_in_tick = 0

        for key in list(self.active_order_history.keys()):
            temp = list(self.active_order_history[key]) # Convert tuple to list
            temp[1] += 1
            self.active_order_history[key] = tuple(temp)
            if self.active_order_history[key][1] > 3:
                self.op_send_cancel_order(key) # This function returns true if cancel is successful
            
                
        
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
        if self.get_projected_op_rate(1) <= 19.5 and len(self.active_order_history) <= 10: # Technically should be 20 - setting it stricter for now
            # Attempting to correct position limits
                    
            self.send_insert_order(client_order_id, side, price, volume, lifespan)
            self.op_history.append(time.time())
            
            # Logging messages
            if side == side.SELL:
                self.logger.warning("We sold!")
            if side == side.BUY:
                self.logger.warning("We bought!")
            #if lifespan == Lifespan.GOOD_FOR_DAY:
            #tuple indices: 0 = order id, 1 = ticks elapsed on order book, 2 = price, 3 = volume, 4 = side of order
            self.active_order_history[client_order_id] = (client_order_id, 0, price, volume, side)

                    

    def op_send_cancel_order(self, client_order_id: int) -> None:
        if self.get_projected_op_rate(1) <= 19.5: # Technically should be 20 - setting it stricter for now
            self.op_history.append(time.time())
            if client_order_id in self.active_order_history:
                self.send_cancel_order(client_order_id)
                del self.active_order_history[client_order_id]
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
        if len(self.op_history) > 0 and (time.time() - self.op_history[0]) != 0:
            return (len(self.op_history)+num_ops)/(time.time() - self.op_history[0])
        else: # If list is empty we can probably do a safe insert since op history has the operations from the past second
            return 0

    def round_to_trade_tick(self, integer):
        return int(integer/100) * 100
        
