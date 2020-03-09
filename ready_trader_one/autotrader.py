import asyncio

from typing import List, Tuple

from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side


class AutoTrader(BaseAutoTrader):

    etf_history = {}
    future_history = {}
    
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)

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
            "ask": [],
            "bid": []
            }

        
        for i in range(5):
            # Entry containing volume and price for given ask/bid
            new_ask_data = {
                "volume": ask_volume[i],
                "price": ask_prices[i]
            }
            
            new_bid_data = {
                "volume": bid_volume[i],
                "price": bid_prices[i]
            }

            # Append data to corresponding list within entry dictionary
            new_entry["ask"].append(new_ask_data)
            new_entry["bid"].append(new_bid_data)

        # Add entry to corresponding instrument dictionary
        if instrument = Instrument.ETF:
            etf_history[str(sequence_number)] = new_entry
            etf_history[str(sequence_number)] = new_entry
        elif instrument = Instrument.FUTURE:
            future_history[str(sequence_number)] = new_entry
            future_history[str(sequence_number)] = new_entry
            
        

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        pass

    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes.

        Since every trade in the ETF is automatically hedged in the future,
        future_position and etf_position will always be the inverse of each
        other (i.e. future_position == -1 * etf_position).
        """
        pass

    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.

        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        if remaining_volume == 0:
            if client_order_id == self.bid_id:
                self.bid_id = 0
            elif client_order_id == self.ask_id:
                self.ask_id = 0

    def collapse_history(history): # Run only if history entries are greater than 200
        if(len(history) >= 200):
            new_entry = {
                }
            for entry in history:
                
            
