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
        self.op_history = [] # Counter of operations - might be obsolete now that we know what "rolling one second period" means
        
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0
        self.trade_tick_list = [] # History of trade ticks
        self.total_fees = 0.0 # Total fees collected
        self.order_ids = itertools.count(1)

        self.base_time = time.time()
        
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
            if len(self.etf_history["history"]) > 0: 
                self.etf_history["average"]["ask"] += new_ask_data["price"]
                self.etf_history["average"]["ask"] /= 2
                self.etf_history["average"]["bid"] += new_bid_data["price"]
                self.etf_history["average"]["bid"] /= 2
            else:
                self.etf_history["average"]["ask"] = new_ask_data["price"]
                self.etf_history["average"]["bid"] = new_bid_data["price"]
            self.etf_history["history"].append(new_entry)
        elif instrument == Instrument.FUTURE:
            if len(self.etf_history["history"]) > 0:
                self.future_history["average"]["ask"] += new_ask_data["price"]
                self.future_history["average"]["ask"] /= 2
                self.future_history["average"]["bid"] += new_bid_data["price"]
                self.future_history["average"]["bid"] /= 2
            else:
                self.future_history["average"]["ask"] = new_ask_data["price"]
                self.future_history["average"]["bid"] = new_bid_data["price"]
            self.future_history["history"].append(new_entry)


        self.logger.warning("Current future dictionary length: %d", len(self.future_history["history"]))
        self.logger.warning("Current ETF dictionary length: %d", len(self.etf_history["history"]))
        self.logger.warning("Boolean Value of if statement: %d", int(len(self.future_history["history"]) < 100 or len(self.etf_history["history"]) < 100))


        def make_order_helper(history):
                total_ask_before_avg = 0
                total_bid_before_avg = 0
                bid_to_ask_ratio = 0.0 
                ratio_history = 0.0
                for i in range(50):
                    ratio_history += sum(history["history"][len(history["history"]) - i - 1]["bid"]["volume"])/(sum(history["history"][len(history["history"]) - i - 1]["ask"]["volume"]))
                
                ratio_history /= 50
                bid_to_ask_ratio = sum(bid_volumes)/sum(ask_volumes)
                new_ask_price = int((history["average"]["ask"]*(1/bid_to_ask_ratio))/100) * 100
                new_bid_price = int((history["average"]["bid"]*bid_to_ask_ratio)/100) * 100
                
                self.logger.warning("New ask price is: %d", new_ask_price)
                self.logger.warning("New bid price is %d", new_bid_price)
                self.ask_id = next(self.order_ids)
                self.op_send_insert_order(self.ask_id, Side.SELL, new_ask_price, 1, Lifespan.FILL_AND_KILL)

                self.bid_id = next(self.order_ids)
                self.op_send_insert_order(self.bid_id, Side.BUY, new_bid_price, 1, Lifespan.FILL_AND_KILL)
                

        #entrance 
        if len(self.future_history["history"]) < 100 or len(self.etf_history["history"]) < 100:
            new_bid_price = bid_prices[0] - self.position * 100 if bid_prices[0] != 0 else 0
            new_ask_price = ask_prices[0] - self.position * 100 if ask_prices[0] != 0 else 0
            
            self.logger.warning("I'm in entrance if statement")

            # These MUST be done in pairs so we do checks manually
            if self.get_projected_op_rate(2) <= 19.5:
                if self.bid_id != 0 and new_bid_price not in (self.bid_price, 0):
                    self.send_cancel_order(self.bid_id)
                    self.bid_id = 0
                    self.op_history.append(time.time())
                    
                if self.ask_id != 0 and new_ask_price not in (self.ask_price, 0):
                    self.send_cancel_order(self.ask_id)
                    self.ask_id = 0
                    self.op_history.append(time.time())
                    
            if self.get_projected_op_rate(2) <= 19.5:
                if self.bid_id == 0 and new_bid_price != 0 and self.position < 100:
                    self.bid_id = next(self.order_ids)
                    self.bid_price = new_bid_price
                    self.send_insert_order(self.bid_id, Side.BUY, new_bid_price, 1, Lifespan.GOOD_FOR_DAY)
                    self.op_history.append(time.time())
                    
                if self.ask_id == 0 and new_ask_price != 0 and self.position > -100:
                    self.ask_id = next(self.order_ids)
                    self.ask_price = new_ask_price
                    self.send_insert_order(self.ask_id, Side.SELL, new_ask_price, 1, Lifespan.GOOD_FOR_DAY)
                    self.op_history.append(time.time())
                    
        #mid-late game

        else:
            self.logger.warning("I'm in mid-late game if statement")
            if instrument == Instrument.FUTURE:
                self.logger.warning("I'm in mid-late-game if future instrument")
                make_order_helper(self.future_history)
                    
            elif instrument == Instrument.ETF: # Isn't this duplicate code?
                self.logger.warning("I'm in mid-late-game if ETF instrument")
                make_order_helper(self.etf_history)

        # Collapse history when number of entries is at least 200
        if len(self.etf_history["history"]) >= 200:
            self.collapse_history(self.etf_history)            
        if len(self.future_history["history"]) >= 200:
            self.collapse_history(self.future_history)
                    
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

        self.total_fees += fees

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
            
    # Helper functions for checking breaches
    def op_send_insert_order(self, client_order_id: int, side: Side, price: int, volume: int, lifespan: Lifespan) -> None:
        if self.get_projected_op_rate(1) <= 19.5: # Technically should be 20 - setting it stricter for now
            self.logger.warning("Goes through 1st if statement for op_send_insert_order")
            if (side == Side.BUY and self.position < 100) or (side == Side.SELL and self.position > -100):
                self.logger.warning("Goes through second if statement for op_send_insert_order")
                self.send_insert_order(client_order_id, side, price, volume, lifespan)
                self.logger.warning("client_order_id of order is %d", client_order_id)
                self.op_history.append(time.time())

    def op_send_cancel_order(self, client_order_id: int) -> None:
        if self.get_projected_op_rate(1) <= 19.5: # Technically should be 20 - setting it stricter for now
            self.send_cancel_order(client_order_id)
            self.op_history.append(time.time())

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
            return len(self.op_history)+num_ops/(time.time() - self.op_history[0])
        else: # If list is empty we can probably do a safe insert since op history has the operations from the past second
            return 0
            
        
