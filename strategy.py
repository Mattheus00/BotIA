"""
strategy.py — Estratégias de entrada e saída com múltiplas confirmações.

Regras invioláveis (v2):
  • Mínimo 3.5 confirmações técnicas para gerar sinal.
  • Nunca operar contra a tendência do 4h.
  • Risk/Reward mínimo de 1:3.
  • Stop Loss baseado em ATR (2x ATR de 14 períodos).
  • Filtro de volatilidade: rejeita ATR > 3% ou < 0.1% do preço.
"""

import numpy as np
import pandas as pd
from binance.client import Client

from config import (
    TF_PRINCIPAL, TF_CONFIRMACAO, TF_TENDENCIA,
    MIN_RR_RATIO, MIN_CONFIRMACOES,
    ATR_MULTIPLIER, ATR_VOL_MAX, ATR_VOL_MIN,
)


# ── INDICADORES MANUAIS (zero dependências externas) ─────────────────────────


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series):
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    return macd_line, signal_line


def _bbands(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    return sma + std_dev * std, sma - std_dev * std


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    plus_dm = high.diff()
    minus_dm = low.diff().apply(lambda x: -x)
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    atr_val = _atr(high, low, close, period)
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr_val.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr_val.replace(0, np.nan))
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.ewm(alpha=1 / period, min_periods=period).mean()


# ── HELPERS ──────────────────────────────────────────────────────────────────


def get_klines(
    client: Client, par: str, interval: str, limit: int = 200
) -> pd.DataFrame:
    """Busca candles da Binance e retorna DataFrame tipado com índice datetime."""
    klines = client.get_klines(symbol=par, interval=interval, limit=limit)
    df = pd.DataFrame(
        klines,
        columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades", "taker_buy",
            "taker_quote", "ignore",
        ],
    )
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df.set_index("timestamp")


def _calcular_indicadores(df_1h: pd.DataFrame, df_15m: pd.DataFrame, df_4h: pd.DataFrame):
    """Adiciona todos os indicadores técnicos aos DataFrames in-place."""

    # RSI
    df_1h["rsi"] = _rsi(df_1h["close"])
    df_15m["rsi"] = _rsi(df_15m["close"])

    # EMAs
    df_1h["ema9"]   = _ema(df_1h["close"], 9)
    df_1h["ema21"]  = _ema(df_1h["close"], 21)
    df_1h["ema50"]  = _ema(df_1h["close"], 50)
    df_4h["ema200"] = _ema(df_4h["close"], 200)

    # MACD
    df_1h["macd"], df_1h["macd_signal"] = _macd(df_1h["close"])

    # Bollinger Bands
    df_1h["bb_upper"], df_1h["bb_lower"] = _bbands(df_1h["close"])

    # ADX
    df_1h["adx"] = _adx(df_1h["high"], df_1h["low"], df_1h["close"])

    # ATR (base do Stop Loss)
    df_1h["atr"] = _atr(df_1h["high"], df_1h["low"], df_1h["close"])

    # Volume médio
    df_1h["vol_ma"] = df_1h["volume"].rolling(20).mean()


# ── FILTRO DE VOLATILIDADE ───────────────────────────────────────────────────


def validar_volatilidade(atr_val: float, preco: float) -> bool:
    """
    Verifica se ATR está dentro de um range aceitável.
    Rejeita ATR > 3% (volátil demais) ou < 0.1% (parado demais).
    """
    if preco <= 0:
        return False
    atr_pct = atr_val / preco
    return ATR_VOL_MIN <= atr_pct <= ATR_VOL_MAX


# ── ANÁLISE PRINCIPAL ────────────────────────────────────────────────────────


def analisar_par(client: Client, par: str) -> dict | None:
    """
    Analisa um par e retorna dicionário com sinal de trade ou None.

    O sinal só é gerado se:
      1. Há pelo menos 3.5 confirmações técnicas.
      2. A direção está alinhada com a tendência do 4h.
      3. O Risk/Reward é >= MIN_RR_RATIO (3.0).
      4. O ATR está dentro do range aceitável.
      5. O Stop Loss é calculado com ATR × 2.0.
    """

    # Buscar dados de 3 timeframes
    df_1h  = get_klines(client, par, TF_PRINCIPAL)
    df_15m = get_klines(client, par, TF_CONFIRMACAO)
    df_4h  = get_klines(client, par, TF_TENDENCIA)

    # Calcular indicadores
    _calcular_indicadores(df_1h, df_15m, df_4h)

    # ── VALORES ATUAIS ────────────────────────────────────────────────────
    c   = df_1h.iloc[-1]
    p   = df_1h.iloc[-2]
    c4h = df_4h.iloc[-1]
    c15 = df_15m.iloc[-1]

    preco = c["close"]
    atr_val = c["atr"]

    # ── FILTRO DE VOLATILIDADE ────────────────────────────────────────────
    if pd.isna(atr_val) or not validar_volatilidade(atr_val, preco):
        return None

    confirmacoes_long  = 0
    confirmacoes_short = 0
    motivos_long  = []
    motivos_short = []

    # ── 1. RSI oversold / overbought ──────────────────────────────────────
    if pd.notna(c["rsi"]) and c["rsi"] < 35:
        confirmacoes_long += 1
        motivos_long.append(f"RSI={c['rsi']:.0f}")
    if pd.notna(c["rsi"]) and c["rsi"] > 65:
        confirmacoes_short += 1
        motivos_short.append(f"RSI={c['rsi']:.0f}")

    # ── 2. EMA 9/21 crossover ────────────────────────────────────────────
    if p["ema9"] < p["ema21"] and c["ema9"] > c["ema21"]:
        confirmacoes_long += 1
        motivos_long.append("EMA9x21↑")
    if p["ema9"] > p["ema21"] and c["ema9"] < c["ema21"]:
        confirmacoes_short += 1
        motivos_short.append("EMA9x21↓")

    # ── 3. Preço vs EMA50 ────────────────────────────────────────────────
    if preco > c["ema50"]:
        confirmacoes_long += 1
        motivos_long.append("Preço>EMA50")
    if preco < c["ema50"]:
        confirmacoes_short += 1
        motivos_short.append("Preço<EMA50")

    # ── 4. MACD cross ────────────────────────────────────────────────────
    if p["macd"] < p["macd_signal"] and c["macd"] > c["macd_signal"]:
        confirmacoes_long += 1
        motivos_long.append("MACD_cross↑")
    if p["macd"] > p["macd_signal"] and c["macd"] < c["macd_signal"]:
        confirmacoes_short += 1
        motivos_short.append("MACD_cross↓")

    # ── 5. Volume acima da média (bônus 0.5) ─────────────────────────────
    vol_ratio = c["volume"] / c["vol_ma"] if c["vol_ma"] > 0 else 0
    if vol_ratio > 1.5:
        confirmacoes_long  += 0.5
        confirmacoes_short += 0.5
        motivos_long.append(f"Vol={vol_ratio:.1f}x")
        motivos_short.append(f"Vol={vol_ratio:.1f}x")

    # ── 6. Confirmação RSI 15m ────────────────────────────────────────────
    if pd.notna(c15["rsi"]) and c15["rsi"] < 40:
        confirmacoes_long += 0.5
        motivos_long.append(f"RSI15m={c15['rsi']:.0f}")
    if pd.notna(c15["rsi"]) and c15["rsi"] > 60:
        confirmacoes_short += 0.5
        motivos_short.append(f"RSI15m={c15['rsi']:.0f}")

    # ── 7. ADX mostrando tendência forte ──────────────────────────────────
    if pd.notna(c["adx"]) and c["adx"] > 25:
        confirmacoes_long  += 0.5
        confirmacoes_short += 0.5
        motivos_long.append(f"ADX={c['adx']:.0f}")
        motivos_short.append(f"ADX={c['adx']:.0f}")

    # ── FILTRO DE TENDÊNCIA 4H ────────────────────────────────────────────
    tendencia_4h_alta = preco > c4h.get("ema200", preco)
    if not tendencia_4h_alta:
        confirmacoes_long = 0
    if tendencia_4h_alta:
        confirmacoes_short = 0

    # ── GERAR SINAL (mín 3.5 conf + SL por ATR + R:R 1:3) ───────────────
    if confirmacoes_long >= MIN_CONFIRMACOES:
        sl = preco - (atr_val * ATR_MULTIPLIER)
        distancia_sl = preco - sl
        tp = preco + distancia_sl * 3.0

        rr = (tp - preco) / distancia_sl if distancia_sl > 0 else 0
        if rr < MIN_RR_RATIO:
            return None

        return {
            "par": par,
            "direcao": "LONG",
            "entry": preco,
            "sl": round(sl, 4),
            "tp": round(tp, 4),
            "confirmacoes": confirmacoes_long,
            "motivo": " | ".join(motivos_long),
        }

    if confirmacoes_short >= MIN_CONFIRMACOES:
        sl = preco + (atr_val * ATR_MULTIPLIER)
        distancia_sl = sl - preco
        tp = preco - distancia_sl * 3.0

        rr = (preco - tp) / distancia_sl if distancia_sl > 0 else 0
        if rr < MIN_RR_RATIO:
            return None

        return {
            "par": par,
            "direcao": "SHORT",
            "entry": preco,
            "sl": round(sl, 4),
            "tp": round(tp, 4),
            "confirmacoes": confirmacoes_short,
            "motivo": " | ".join(motivos_short),
        }

    return None
