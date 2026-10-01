from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from freqtrade.strategy.interface import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class EmaTrendV1(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short: bool = True
    
    minimal_roi = {
        "0": 0.02,
        "30": 0.015,
        "60": 0.01,
        "120": 0.005
    }
    
    stoploss = -0.02
    
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.015
    trailing_only_offset_is_reached = True
    
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    
    process_only_new_candles = True
    startup_candle_count: int = 50
    
    order_types = {
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': True,
    }
    
    order_time_in_force = {
        'entry': 'GTC',
        'exit': 'GTC'
    }
    
    plot_config = {
        'main_plot': {
            'ema_fast': {'color': 'blue'},
            'ema_slow': {'color': 'orange'},
        },
        'subplots': {
            "ADX": {
                'adx': {'color': 'red'},
            },
            "RSI": {
                'rsi': {'color': 'purple'},
            },
        }
    }
    
    ema_fast_period = IntParameter(5, 20, default=9, space="buy", optimize=True)
    ema_slow_period = IntParameter(15, 50, default=21, space="buy", optimize=True)
    adx_period = IntParameter(10, 20, default=14, space="buy", optimize=True)
    adx_min = DecimalParameter(15, 30, default=20, decimals=0, space="buy", optimize=True)
    rsi_period = IntParameter(10, 20, default=14, space="buy", optimize=True)
    rsi_overbought = IntParameter(65, 80, default=70, space="buy", optimize=True)
    rsi_oversold = IntParameter(20, 35, default=30, space="buy", optimize=True)
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.ema_fast_period.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.ema_slow_period.value)
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=self.adx_period.value)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        dataframe['ema_cross_up'] = qtpylib.crossed_above(dataframe['ema_fast'], dataframe['ema_slow'])
        dataframe['ema_cross_down'] = qtpylib.crossed_below(dataframe['ema_fast'], dataframe['ema_slow'])
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions_long = [
            dataframe['ema_cross_up'],
            dataframe['adx'] > self.adx_min.value,
            dataframe['rsi'] < self.rsi_overbought.value,
            dataframe['volume'] > 0,
        ]
        
        conditions_short = [
            dataframe['ema_cross_down'],
            dataframe['adx'] > self.adx_min.value,
            dataframe['rsi'] > self.rsi_oversold.value,
            dataframe['volume'] > 0,
        ]
        
        if conditions_long:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions_long),
                'enter_long'] = 1
        
        if conditions_short:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions_short),
                'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions_exit_long = [
            dataframe['ema_cross_down'],
            dataframe['volume'] > 0,
        ]
        
        conditions_exit_short = [
            dataframe['ema_cross_up'],
            dataframe['volume'] > 0,
        ]
        
        if conditions_exit_long:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions_exit_long),
                'exit_long'] = 1
        
        if conditions_exit_short:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions_exit_short),
                'exit_short'] = 1
        
        return dataframe


def reduce(op, seq):
    from functools import reduce
    return reduce(op, seq)