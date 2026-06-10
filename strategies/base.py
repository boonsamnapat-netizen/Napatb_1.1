from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame, market_df: pd.DataFrame = None) -> pd.Series:
        """Return pd.Series[int] with 1 = buy signal, 0 = no signal, indexed by date."""

    @abstractmethod
    def name(self) -> str:
        pass
