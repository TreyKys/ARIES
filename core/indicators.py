import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

def compute_sma(df: pd.DataFrame, period: int) -> pd.Series:
    """Compute Simple Moving Average."""
    try:
        return df['close'].rolling(window=period).mean()
    except Exception as e:
        logger.error(f"Error computing SMA: {e}")
        return pd.Series(index=df.index, dtype=float)

def compute_ema(df: pd.DataFrame, period: int) -> pd.Series:
    """Compute Exponential Moving Average."""
    try:
        return df['close'].ewm(span=period, adjust=False).mean()
    except Exception as e:
        logger.error(f"Error computing EMA: {e}")
        return pd.Series(index=df.index, dtype=float)

def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Relative Strength Index."""
    try:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    except Exception as e:
        logger.error(f"Error computing RSI: {e}")
        return pd.Series(index=df.index, dtype=float)

def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range."""
    try:
        high = df['high']
        low = df['low']
        close_prev = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = (high - close_prev).abs()
        tr3 = (low - close_prev).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.ewm(alpha=1/period, adjust=False).mean()
    except Exception as e:
        logger.error(f"Error computing ATR: {e}")
        return pd.Series(index=df.index, dtype=float)

def compute_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Compute MACD, Signal, and Histogram."""
    try:
        fast_ema = compute_ema(df, fast)
        slow_ema = compute_ema(df, slow)
        macd = fast_ema - slow_ema
        sig = macd.ewm(span=signal, adjust=False).mean()
        hist = macd - sig
        return pd.DataFrame({'macd': macd, 'signal': sig, 'histogram': hist}, index=df.index)
    except Exception as e:
        logger.error(f"Error computing MACD: {e}")
        return pd.DataFrame(columns=['macd', 'signal', 'histogram'], index=df.index)

def compute_bollinger(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    """Compute Bollinger Bands."""
    try:
        sma = compute_sma(df, period)
        roll_std = df['close'].rolling(window=period).std()
        upper = sma + (roll_std * std)
        lower = sma - (roll_std * std)
        width = upper - lower
        return pd.DataFrame({'upper': upper, 'middle': sma, 'lower': lower, 'width': width}, index=df.index)
    except Exception as e:
        logger.error(f"Error computing Bollinger Bands: {e}")
        return pd.DataFrame(columns=['upper', 'middle', 'lower', 'width'], index=df.index)

def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average Directional Index (ADX)."""
    try:
        up = df['high'] - df['high'].shift(1)
        down = df['low'].shift(1) - df['low']
        
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)
        
        tr_smooth = compute_atr(df, period)
        
        plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / tr_smooth
        minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / tr_smooth
        
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1))
        adx = dx.ewm(alpha=1/period, adjust=False).mean()
        return adx
    except Exception as e:
        logger.error(f"Error computing ADX: {e}")
        return pd.Series(index=df.index, dtype=float)

def compute_volume_delta(trades_data: list[dict]) -> float:
    """
    Compute Cumulative Volume Delta (CVD) from list of trades.
    Positive indicates buy pressure.
    """
    try:
        cvd = 0.0
        for trade in trades_data:
            amount = float(trade.get('amount', 0.0))
            side = str(trade.get('side', '')).lower()
            if side == 'buy':
                cvd += amount
            elif side == 'sell':
                cvd -= amount
        return cvd
    except Exception as e:
        logger.error(f"Error computing volume delta: {e}")
        return 0.0

def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Compute and append all indicators to the dataframe."""
    try:
        df = df.copy()
        df['rsi'] = compute_rsi(df)
        df['atr'] = compute_atr(df)
        df['ema50'] = compute_ema(df, 50)
        df['ema200'] = compute_ema(df, 200)
        df['sma20'] = compute_sma(df, 20)
        
        macd_df = compute_macd(df)
        df['macd'] = macd_df['macd']
        df['macd_signal'] = macd_df['signal']
        df['macd_hist'] = macd_df['histogram']
        
        bb_df = compute_bollinger(df)
        df['bb_upper'] = bb_df['upper']
        df['bb_middle'] = bb_df['middle']
        df['bb_lower'] = bb_df['lower']
        df['bb_width'] = bb_df['width']
        
        df['adx'] = compute_adx(df)
        
        return df
    except Exception as e:
        logger.error(f"Error in compute_all: {e}")
        return df
