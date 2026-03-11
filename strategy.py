"""
strategy.py — Estratégias de entrada e saída com múltiplas confirmações.

Regras invioláveis (ATUALIZADAS v2):
  • Mínimo 3.5 confirmações técnicas para gerar sinal.
  • Nunca operar contra a tendência do 4h.
  • Risk/Reward mínimo de 1:3.
  • Stop Loss baseado em ATR (2x ATR de 14 períodos).
  • Filtro de volatilidade: rejeita ATR > 3% ou < 0.1% do preço.
"""

import pandas as pd
import pandas_ta as ta
from binance.client import Client

from config import (
    TF_PRINCIPAL, TF_CONFIRMACAO, TF_TENDENCIA,
    MIN_RR_RATIO, MIN_CONFIRMACOES,
    ATR_MULTIPLIER, ATR_VOL_MAX, ATR_VOL_MIN,
)


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

    # ── RSI ────────────────────────────────────────────────────────────────
    df_1h["rsi"] = ta.rsi(df_1h["close"], length=14)
    df_15m["rsi"] = ta.rsi(df_15m["close"], length=14)

    # ── EMAs ───────────────────────────────────────────────────────────────
    df_1h["ema9"]   = ta.ema(df_1h["close"], length=9)
    df_1h["ema21"]  = ta.ema(df_1h["close"], length=21)
    df_1h["ema50"]  = ta.ema(df_1h["close"], length=50)
    df_4h["ema200"] = ta.ema(df_4h["close"], length=200)

    # ── MACD ───────────────────────────────────────────────────────────────
    macd = ta.macd(df_1h["close"])
    df_1h["macd"]        = macd["MACD_12_26_9"]
    df_1h["macd_signal"] = macd["MACDs_12_26_9"]

    # ── Bollinger Bands ────────────────────────────────────────────────────
    bb = ta.bbands(df_1h["close"], length=20)
    df_1h["bb_upper"] = bb["BBU_20_2.0"]
    df_1h["bb_lower"] = bb["BBL_20_2.0"]
    df_1h["bb_width"] = bb["BBB_20_2.0"]

    # ── ADX (força da tendência) ───────────────────────────────────────────
    adx = ta.adx(df_1h["high"], df_1h["low"], df_1h["close"])
    df_1h["adx"] = adx["ADX_14"]

    # ── ATR (Average True Range — base do Stop Loss) ──────────────────────
    df_1h["atr"] = ta.atr(df_1h["high"], df_1h["low"], df_1h["close"], length=14)

    # ── Volume médio 20 períodos ───────────────────────────────────────────
    df_1h["vol_ma"] = df_1h["volume"].rolling(20).mean()


# ── FILTRO DE VOLATILIDADE ───────────────────────────────────────────────────


def validar_volatilidade(atr: float, preco: float) -> bool:
    """
    Verifica se o ATR está dentro de um range aceitável.

    Rejeita:
      - ATR > 3% do preço → mercado volátil demais, SLs serão gigantes
      - ATR < 0.1% do preço → mercado parado demais, sem oportunidade

    Returns:
        True se a volatilidade é aceitável para operar.
    """
    if preco <= 0:
        return False

    atr_pct = atr / preco

    if atr_pct > ATR_VOL_MAX:
        return False  # Volátil demais

    if atr_pct < ATR_VOL_MIN:
        return False  # Parado demais

    return True


# ── ANÁLISE PRINCIPAL ────────────────────────────────────────────────────────


def analisar_par(client: Client, par: str) -> dict | None:
    """
    Analisa um par e retorna dicionário com sinal de trade ou None.

    O sinal só é gerado se:
      1. Há pelo menos 4 confirmações técnicas.
      2. A direção está alinhada com a tendência do 4h.
      3. O Risk/Reward é >= MIN_RR_RATIO (3.0).
      4. O ATR está dentro do range aceitável (0.1% a 3% do preço).
      5. O Stop Loss é calculado com base em ATR * 2.0.
    """

    # Buscar dados de 3 timeframes
    df_1h  = get_klines(client, par, TF_PRINCIPAL)
    df_15m = get_klines(client, par, TF_CONFIRMACAO)
    df_4h  = get_klines(client, par, TF_TENDENCIA)

    # Calcular indicadores
    _calcular_indicadores(df_1h, df_15m, df_4h)

    # ── VALORES ATUAIS ────────────────────────────────────────────────────
    c   = df_1h.iloc[-1]   # candle atual  1h
    p   = df_1h.iloc[-2]   # candle anterior 1h
    c4h = df_4h.iloc[-1]   # candle atual  4h
    c15 = df_15m.iloc[-1]  # candle atual 15m

    preco = c["close"]
    atr   = c["atr"]

    # ── FILTRO DE VOLATILIDADE ────────────────────────────────────────────
    if pd.isna(atr) or not validar_volatilidade(atr, preco):
        return None

    confirmacoes_long  = 0
    confirmacoes_short = 0
    motivos_long  = []
    motivos_short = []

    # ── 1. RSI oversold / overbought ──────────────────────────────────────
    if c["rsi"] < 35:
        confirmacoes_long += 1
        motivos_long.append(f"RSI={c['rsi']:.0f}")
    if c["rsi"] > 65:
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
    if c15["rsi"] < 40:
        confirmacoes_long += 0.5
        motivos_long.append(f"RSI15m={c15['rsi']:.0f}")
    if c15["rsi"] > 60:
        confirmacoes_short += 0.5
        motivos_short.append(f"RSI15m={c15['rsi']:.0f}")

    # ── 7. ADX mostrando tendência forte ──────────────────────────────────
    if c["adx"] > 25:
        confirmacoes_long  += 0.5
        confirmacoes_short += 0.5
        motivos_long.append(f"ADX={c['adx']:.0f}")
        motivos_short.append(f"ADX={c['adx']:.0f}")

    # ── FILTRO DE TENDÊNCIA 4H ────────────────────────────────────────────
    # Só opera a favor da tendência principal
    tendencia_4h_alta = preco > c4h.get("ema200", preco)
    if not tendencia_4h_alta:
        confirmacoes_long = 0   # Bloqueia longs contra tendência
    if tendencia_4h_alta:
        confirmacoes_short = 0  # Bloqueia shorts contra tendência

    # ── GERAR SINAL (mínimo 4 confirmações + SL por ATR + R:R 1:3) ───────
    if confirmacoes_long >= MIN_CONFIRMACOES:
        sl = preco - (atr * ATR_MULTIPLIER)   # SL baseado em ATR
        distancia_sl = preco - sl
        tp = preco + distancia_sl * 3.0       # R:R 1:3

        # Verificar R:R mínimo
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
        sl = preco + (atr * ATR_MULTIPLIER)   # SL baseado em ATR
        distancia_sl = sl - preco
        tp = preco - distancia_sl * 3.0       # R:R 1:3

        # Verificar R:R mínimo
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
