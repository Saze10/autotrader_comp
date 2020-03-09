import asyncio
from typing import List, Tuple
from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side
import time
import itertools

class AutoTrader(BaseAutoTrader):
    
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        
        self.etf_history = {"start_key": 0, "average": {"ask":0, "bid":0}, "history":[]}
    
        self.future_history = {"start_key": 0, "average": {"ask":0, "bid":0}, "history":[]}

        self.op_count = 0

        self.base_time = time.time()
        
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0

        self.trade_tick_list = []

        self.total_fees = 0.0

        self.order_ids = itertools.count(1)


    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.
        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.
        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """

        # Entry containing ask and bid prices for given instrument
        new_entry = {
            "ask": 0,
            "bid": 0
        }

        
        # Entry containing volume and price for given ask/bid
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

        # Add entry to corresponding instrument dictionary
        if instrument == Instrument.ETF:
            self.etf_history["history"].append(new_entry)
        elif instrument == Instrument.FUTURE:
            self.future_history["history"].append(new_entry)

        if len(self.etf_history["history"]) >= 200:
            self.collapse_history(self.etf_history)            
        if len(self.future_history["history"]) >= 200:
            self.collapse_history(self.future_history)


        #entrance 
        if len(self.future_history["history"]) < 100 or len(self.etf_history["history"]) < 100:
            new_bid_price = bid_prices[0] - self.position * 100 if bid_prices[0] != 0 else 0
            new_ask_price = ask_prices[0] - self.position * 100 if ask_prices[0] != 0 else 0

            if self.op_count < 19:
                if self.bid_id != 0 and new_bid_price not in (self.bid_price, 0):
                    self.send_cancel_order(self.bid_id)
                    self.bid_id = 0
                    self.op_count += 1
                    
                if self.ask_id != 0 and new_ask_price not in (self.ask_price, 0):
                    self.send_cancel_order(self.ask_id)
                    self.ask_id = 0
                    self.op_count += 1

            if self.op_count < 19:
                if self.bid_id == 0 and new_bid_price != 0 and self.position < 100:
                    self.bid_id = next(self.order_ids)
                    self.bid_price = new_bid_price
                    self.send_insert_order(self.bid_id, Side.BUY, new_bid_price, 1, Lifespan.GOOD_FOR_DAY)
                    self.op_count += 1

                if self.ask_id == 0 and new_ask_price != 0 and self.position > -100:
                    self.ask_id = next(self.order_ids)
                    self.ask_price = new_ask_price
                    self.send_insert_order(self.ask_id, Side.SELL, new_ask_price, 1, Lifespan.GOOD_FOR_DAY)
                    self.op_count += 1
                    

        #mid-late game
        else:
            if instrument == Instrument.FUTURE:

                total_ask_before_avg = 0
                total_bid_before_avg = 0
                bid_to_ask_ratio = 0.0 #current bid to ask volume ratio
                ratio_history = 0.0 #historic bid to ask volume ratio (past 50 order books)
                
                for i in range(50):
                    ratio_history += sum(self.future_history["history"][len(self.future_history["history"]) - i - 1]["bid"]["volume"])/(sum(self.future_history["history"][len(self.future_history["history"]) - i - 1]["ask"]["volume"]))

                ratio_history /= 50

                bid_to_ask_ratio = sum(bid_volumes)/sum(ask_volumes)

                new_ask_price = self.etf_history["average"]["ask"]*(1/bid_to_ask_ratio)
                new_bid_price = self.etf_history["average"]["bid"]*bid_to_ask_ratio

                if self.op_count < 20:                    
                    self.send_insert_order(self.ask_id, Side.SELL, new_ask_price, 1, Lifespan.FILL_AND_KILL)
                    self.op_count += 1
                    
                if self.op_count < 20:
                    self.send_insert_order(self.bid_id, Side.BUY, new_bid_price, 1, Lifespan.FILL_AND_KILL)
                    self.op_count += 1

            elif instrument == Instrument.ETF:

                total_ask_before_avg = 0
                total_bid_before_avg = 0
                bid_to_ask_ratio = 0.0 
                ratio_history = 0.0

                for i in range(50):
                    ratio_history += sum(self.etf_history["history"][len(self.etf_history["history"]) - i - 1]["volume"])/(sum(self.etf_history["history"][len(self.etf_history["history"]) - i - 1]["volume"]))
                
                ratio_history /= 50

                bid_to_ask_ratio = sum(bid_volumes)/sum(ask_volumes)

                new_ask_price = self.future_history["average"]["ask"]*(1/bid_to_ask_ratio)
                new_bid_price = self.future_history["average"]["bid"]*bid_to_ask_ratio

                if self.op_count < 20:                   
                    self.send_insert_order(self.ask_id, Side.SELL, new_ask_price, 1, Lifespan.FILL_AND_KILL)
                    self.op_count += 1
                if self.op_count < 20:
                    self.send_insert_order(self.bid_id, Side.BUY, new_bid_price, 1, Lifespan.FILL_AND_KILL)
                    self.op_count += 1


        # check if we need to reset the timer and op count - happens every seconds
        if time.time() - self.base_time >= 0.99999:
            self.base_time = time.time()
            self.op_count = 0

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes.
        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.
        If an order is cancelled its remaining volume will be zero.
        """
        self.total_fees += fees
        
        if remaining_volume != 0:
            if self.op_count < 20:
                self.send_amend_order(client_order_id, int(remaining_volume * 1.1))
                #dont know what the third parameter for the above should be. Need concrete position information to implement this properly 
                self.op_count += 1
            
        if time.time() - self.base_time >= 0.99999:
            self.base_time = time.time()
            self.op_count = 0

        

    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes.
        Since every trade in the ETF is automatically hedged in the future,
        future_position and etf_position will always be the inverse of each
        other (i.e. future_position == -1 * etf_position).
        """
        self.position = future_position + etf_position

    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.
        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        self.trade_tick_list.append(trade_ticks) 

    def collapse_history(self, history): # Run only if history entries are greater than or equal to 202 - accounting for the two
        if(len(history["history"]) >= 200): # Making sure we avoid key errors
            avg_entry = {
            "ask": 0,
            "bid": 0
            }
            
            # Loop through the history's entries
            for i in range(100):
                avg_entry["ask"] += history["history"][i]["ask"]["price"]
                avg_entry["bid"] += history["history"][i]["bid"]["price"]
                

            # Get the average
            avg_entry["ask"] /= 100
            avg_entry["bid"] /= 100

            for i in range(100):
                del history["history"][0]

            # Update the average dictionary entry
            history["average"] = avg_entry
