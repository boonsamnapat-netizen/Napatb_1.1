"""Alpaca paper-trading broker wrapper for NAPATB AI Trading."""

import os

try:
    import alpaca_trade_api as tradeapi
    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False

_PAPER_BASE_URL = 'https://paper-api.alpaca.markets'


class AlpacaBroker:
    """Thin wrapper around the Alpaca REST API for paper trading."""

    def __init__(self, paper: bool = True):
        if not _ALPACA_AVAILABLE:
            raise RuntimeError('alpaca-trade-api not installed')
        api_key    = os.environ.get('ALPACA_API_KEY', '')
        secret_key = os.environ.get('ALPACA_SECRET_KEY', '')
        if not api_key or not secret_key:
            raise RuntimeError('ALPACA_API_KEY / ALPACA_SECRET_KEY not set')
        base_url = _PAPER_BASE_URL if paper else 'https://api.alpaca.markets'
        self.api = tradeapi.REST(api_key, secret_key, base_url, api_version='v2')

    def get_equity(self) -> float:
        """Return current portfolio equity."""
        account = self.api.get_account()
        return float(account.equity)

    def get_positions(self) -> list:
        """Return open positions as list of dicts."""
        positions = []
        for p in self.api.list_positions():
            positions.append({
                'ticker':           p.symbol,
                'qty':              float(p.qty),
                'cost_basis':       float(p.cost_basis),
                'current_price':    float(p.current_price),
                'unrealized_pnl':   float(p.unrealized_pl),
            })
        return positions

    def place_market_order(self, ticker: str, qty: float, side: str = 'buy'):
        """Place a market order. Returns order_id or None on error."""
        try:
            order = self.api.submit_order(
                symbol=ticker,
                qty=qty,
                side=side,
                type='market',
                time_in_force='day',
            )
            return order.id
        except Exception as e:
            print(f'[Alpaca] place_market_order error ({ticker}): {e}')
            return None

    def place_stop_order(self, ticker: str, qty: float, stop_price: float):
        """Place a stop-loss order. Returns order_id or None on error."""
        try:
            order = self.api.submit_order(
                symbol=ticker,
                qty=qty,
                side='sell',
                type='stop',
                time_in_force='gtc',
                stop_price=round(stop_price, 2),
            )
            return order.id
        except Exception as e:
            print(f'[Alpaca] place_stop_order error ({ticker}): {e}')
            return None

    def close_position(self, ticker: str) -> bool:
        """Close entire position for ticker. Returns True on success."""
        try:
            self.api.close_position(ticker)
            return True
        except Exception as e:
            print(f'[Alpaca] close_position error ({ticker}): {e}')
            return False

    def cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        try:
            self.api.cancel_all_orders()
        except Exception as e:
            print(f'[Alpaca] cancel_all_orders error: {e}')

    def get_open_orders(self) -> list:
        """Return list of open orders."""
        try:
            return self.api.list_orders(status='open')
        except Exception as e:
            print(f'[Alpaca] get_open_orders error: {e}')
            return []
