"""
backtest.py — Simulador / Backtester do Trading Bot.

Usa dados históricos REAIS da Binance (API pública, sem API key).
Calcula indicadores manualmente (sem dependência de pandas-ta).

Uso:
    python backtest.py

Gera relatório detalhado com:
  • Trades executados (entry, SL, TP, resultado)
  • PnL acumulado, win rate, profit factor
  • Drawdown máximo
  • Gráfico em ASCII do equity curve
"""

import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests


# ══════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DO BACKTEST
# ══════════════════════════════════════════════════════════════════════

CAPITAL_INICIAL = 1000.0
RISCO_POR_TRADE = 0.01
MAX_POSICOES = 5
DRAWDOWN_MAX = 0.03
MIN_RR_RATIO = 3.0
MAX_PCT_SALDO = 0.20
MIN_CONFIRMACOES = 3.5

# ATR
ATR_MULTIPLIER = 2.0
ATR_VOL_MAX = 0.03    # 3% do preço
ATR_VOL_MIN = 0.001   # 0.1% do preço

PARES = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT"]
DIAS_BACKTEST = 30

BASE_URL = "https://api.binance.com"


# ══════════════════════════════════════════════════════════════════════
# INDICADORES MANUAIS (sem pandas-ta)
# ══════════════════════════════════════════════════════════════════════

def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_macd(close: pd.Series):
    ema12 = calc_ema(close, 12)
    ema26 = calc_ema(close, 26)
    macd_line = ema12 - ema26
    signal_line = calc_ema(macd_line, 9)
    return macd_line, signal_line

def calc_bbands(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, lower

def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()

def calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    plus_dm = high.diff()
    minus_dm = low.diff().apply(lambda x: -x)
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    atr = calc_atr(high, low, close, period)
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr.replace(0, np.nan))
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1/period, min_periods=period).mean()
    return adx


# ══════════════════════════════════════════════════════════════════════
# DADOS
# ══════════════════════════════════════════════════════════════════════

def fetch_klines(par: str, interval: str, days: int) -> pd.DataFrame:
    limit = min(days * {"1h": 24, "4h": 6, "15m": 96}.get(interval, 24), 1000)
    url = f"{BASE_URL}/api/v3/klines"
    params = {"symbol": par, "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ⚠️  Erro ao buscar {par} {interval}: {e}")
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_buy", "taker_quote", "ignore",
    ])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df.set_index("timestamp")


def add_indicators(df_1h, df_4h, df_15m):
    if df_1h.empty or df_4h.empty or df_15m.empty:
        return
    df_1h["rsi"] = calc_rsi(df_1h["close"])
    df_15m["rsi"] = calc_rsi(df_15m["close"])
    df_1h["ema9"]   = calc_ema(df_1h["close"], 9)
    df_1h["ema21"]  = calc_ema(df_1h["close"], 21)
    df_1h["ema50"]  = calc_ema(df_1h["close"], 50)
    df_4h["ema200"] = calc_ema(df_4h["close"], 200)
    df_1h["macd"], df_1h["macd_signal"] = calc_macd(df_1h["close"])
    df_1h["bb_upper"], df_1h["bb_lower"] = calc_bbands(df_1h["close"])
    df_1h["adx"] = calc_adx(df_1h["high"], df_1h["low"], df_1h["close"])
    df_1h["atr"] = calc_atr(df_1h["high"], df_1h["low"], df_1h["close"])
    df_1h["vol_ma"] = df_1h["volume"].rolling(20).mean()


# ══════════════════════════════════════════════════════════════════════
# FILTRO DE VOLATILIDADE
# ══════════════════════════════════════════════════════════════════════

def validar_volatilidade(atr, preco):
    """ATR deve estar entre 0.1% e 3% do preço."""
    if preco <= 0 or pd.isna(atr):
        return False
    atr_pct = atr / preco
    return ATR_VOL_MIN <= atr_pct <= ATR_VOL_MAX


# ══════════════════════════════════════════════════════════════════════
# LÓGICA DE SINAIS (v2 — ATR SL, 4 conf, R:R 1:3, filtro vol)
# ══════════════════════════════════════════════════════════════════════

def check_signal(c, p, c4h, c15m, preco):
    # Filtro de volatilidade
    atr = c.get("atr")
    if not validar_volatilidade(atr, preco):
        return None

    conf_long = 0
    conf_short = 0
    mot_l, mot_s = [], []

    # 1. RSI
    rsi = c.get("rsi")
    if pd.notna(rsi):
        if rsi < 35: conf_long += 1; mot_l.append(f"RSI={rsi:.0f}")
        if rsi > 65: conf_short += 1; mot_s.append(f"RSI={rsi:.0f}")

    # 2. EMA crossover
    vals = [p.get("ema9"), p.get("ema21"), c.get("ema9"), c.get("ema21")]
    if all(pd.notna(v) for v in vals):
        if p["ema9"] < p["ema21"] and c["ema9"] > c["ema21"]:
            conf_long += 1; mot_l.append("EMA9x21↑")
        if p["ema9"] > p["ema21"] and c["ema9"] < c["ema21"]:
            conf_short += 1; mot_s.append("EMA9x21↓")

    # 3. Preço vs EMA50
    if pd.notna(c.get("ema50")):
        if preco > c["ema50"]: conf_long += 1; mot_l.append(">EMA50")
        else: conf_short += 1; mot_s.append("<EMA50")

    # 4. MACD cross
    macd_vals = [p.get("macd"), p.get("macd_signal"), c.get("macd"), c.get("macd_signal")]
    if all(pd.notna(v) for v in macd_vals):
        if p["macd"] < p["macd_signal"] and c["macd"] > c["macd_signal"]:
            conf_long += 1; mot_l.append("MACD↑")
        if p["macd"] > p["macd_signal"] and c["macd"] < c["macd_signal"]:
            conf_short += 1; mot_s.append("MACD↓")

    # 5. Volume
    if pd.notna(c.get("vol_ma")) and c["vol_ma"] > 0:
        vr = c["volume"] / c["vol_ma"]
        if vr > 1.5:
            conf_long += 0.5; conf_short += 0.5
            mot_l.append(f"Vol={vr:.1f}x"); mot_s.append(f"Vol={vr:.1f}x")

    # 6. RSI 15m
    rsi15 = c15m.get("rsi")
    if pd.notna(rsi15):
        if rsi15 < 40: conf_long += 0.5; mot_l.append(f"RSI15m={rsi15:.0f}")
        if rsi15 > 60: conf_short += 0.5; mot_s.append(f"RSI15m={rsi15:.0f}")

    # 7. ADX
    adx = c.get("adx")
    if pd.notna(adx) and adx > 25:
        conf_long += 0.5; conf_short += 0.5
        mot_l.append(f"ADX={adx:.0f}"); mot_s.append(f"ADX={adx:.0f}")

    # Filtro tendência 4h
    ema200 = c4h.get("ema200")
    if pd.notna(ema200):
        if preco <= ema200: conf_long = 0
        if preco > ema200: conf_short = 0

    # Sinal LONG (mín 4 conf, SL por ATR, R:R 1:3)
    if conf_long >= MIN_CONFIRMACOES:
        sl = preco - (atr * ATR_MULTIPLIER)
        dist = preco - sl
        tp = preco + dist * 3.0
        if dist > 0 and (tp - preco) / dist >= MIN_RR_RATIO:
            return {"direcao": "LONG", "entry": preco, "sl": round(sl, 4),
                    "tp": round(tp, 4), "confirmacoes": conf_long,
                    "motivo": " | ".join(mot_l)}

    # Sinal SHORT (mín 4 conf, SL por ATR, R:R 1:3)
    if conf_short >= MIN_CONFIRMACOES:
        sl = preco + (atr * ATR_MULTIPLIER)
        dist = sl - preco
        tp = preco - dist * 3.0
        if dist > 0 and (preco - tp) / dist >= MIN_RR_RATIO:
            return {"direcao": "SHORT", "entry": preco, "sl": round(sl, 4),
                    "tp": round(tp, 4), "confirmacoes": conf_short,
                    "motivo": " | ".join(mot_s)}

    return None


# ══════════════════════════════════════════════════════════════════════
# MOTOR DE BACKTEST
# ══════════════════════════════════════════════════════════════════════

class BacktestEngine:
    def __init__(self):
        self.capital = CAPITAL_INICIAL
        self.saldo = CAPITAL_INICIAL
        self.posicoes_abertas = []
        self.trades_fechados = []
        self.equity_curve = [CAPITAL_INICIAL]
        self.max_drawdown = 0.0
        self.peak_equity = CAPITAL_INICIAL
        self.pnl_dia = 0.0
        self.dia_atual = ""

    def _calc_tamanho(self, entry, sl):
        dist = abs(entry - sl)
        if dist == 0 or entry <= 0: return 0.0
        risco_usdt = self.saldo * RISCO_POR_TRADE
        qty = risco_usdt / dist
        max_qty = (self.saldo * MAX_PCT_SALDO) / entry
        return min(qty, max_qty)

    def abrir(self, par, sinal, timestamp):
        if len(self.posicoes_abertas) >= MAX_POSICOES: return False
        if abs(self.pnl_dia) >= self.capital * DRAWDOWN_MAX: return False
        qty = self._calc_tamanho(sinal["entry"], sinal["sl"])
        if qty <= 0: return False
        self.posicoes_abertas.append({
            "par": par, **sinal, "qty": qty,
            "timestamp_open": timestamp, "timestamp_close": None,
            "resultado": None, "pnl": 0.0,
        })
        return True

    def verificar(self, par, high, low, timestamp):
        for pos in self.posicoes_abertas[:]:
            if pos["par"] != par: continue
            hit_sl = hit_tp = False
            if pos["direcao"] == "LONG":
                if low <= pos["sl"]: hit_sl = True
                elif high >= pos["tp"]: hit_tp = True
            else:
                if high >= pos["sl"]: hit_sl = True
                elif low <= pos["tp"]: hit_tp = True

            if hit_sl or hit_tp:
                exit_price = pos["sl"] if hit_sl else pos["tp"]
                if pos["direcao"] == "LONG":
                    pnl = (exit_price - pos["entry"]) * pos["qty"]
                else:
                    pnl = (pos["entry"] - exit_price) * pos["qty"]
                pos["resultado"] = "SL" if hit_sl else "TP"
                pos["pnl"] = round(pnl, 4)
                pos["timestamp_close"] = timestamp
                self.saldo += pnl
                self.pnl_dia += pnl
                self.trades_fechados.append(pos)
                self.posicoes_abertas.remove(pos)
                self._update_eq()

    def _update_eq(self):
        self.equity_curve.append(round(self.saldo, 2))
        if self.saldo > self.peak_equity: self.peak_equity = self.saldo
        dd = (self.peak_equity - self.saldo) / self.peak_equity if self.peak_equity > 0 else 0
        self.max_drawdown = max(self.max_drawdown, dd)

    def novo_dia(self, dia):
        if dia != self.dia_atual:
            self.dia_atual = dia
            self.pnl_dia = 0.0

    def relatorio(self):
        total = len(self.trades_fechados)
        wins = [t for t in self.trades_fechados if t["pnl"] > 0]
        losses = [t for t in self.trades_fechados if t["pnl"] <= 0]
        tp = sum(t["pnl"] for t in wins)
        tl = abs(sum(t["pnl"] for t in losses))
        pnl = sum(t["pnl"] for t in self.trades_fechados)
        wr = (len(wins)/total*100) if total > 0 else 0
        pf = (tp/tl) if tl > 0 else float('inf')
        aw = (tp/len(wins)) if wins else 0
        al = (tl/len(losses)) if losses else 0
        ret = ((self.saldo - CAPITAL_INICIAL) / CAPITAL_INICIAL) * 100

        best = max(self.trades_fechados, key=lambda t: t["pnl"]) if total else None
        worst = min(self.trades_fechados, key=lambda t: t["pnl"]) if total else None

        sw = sl = msw = msl = 0
        for t in self.trades_fechados:
            if t["pnl"] > 0: sw += 1; sl = 0
            else: sl += 1; sw = 0
            msw = max(msw, sw); msl = max(msl, sl)

        by_pair = {}
        for t in self.trades_fechados:
            p = t["par"]
            if p not in by_pair: by_pair[p] = {"trades": 0, "wins": 0, "pnl": 0.0}
            by_pair[p]["trades"] += 1; by_pair[p]["pnl"] += t["pnl"]
            if t["pnl"] > 0: by_pair[p]["wins"] += 1

        return {
            "periodo": DIAS_BACKTEST, "capital_i": CAPITAL_INICIAL,
            "capital_f": round(self.saldo, 2), "pnl": round(pnl, 2),
            "ret": round(ret, 2), "total": total, "wins": len(wins),
            "losses": len(losses), "wr": round(wr, 1), "pf": round(pf, 2),
            "aw": round(aw, 2), "al": round(al, 2),
            "mdd": round(self.max_drawdown*100, 2),
            "longs": len([t for t in self.trades_fechados if t["direcao"]=="LONG"]),
            "shorts": len([t for t in self.trades_fechados if t["direcao"]=="SHORT"]),
            "best": best, "worst": worst, "msw": msw, "msl": msl,
            "by_pair": by_pair, "trades": self.trades_fechados,
            "equity": self.equity_curve,
        }


# ══════════════════════════════════════════════════════════════════════
# ASCII CHART
# ══════════════════════════════════════════════════════════════════════

def ascii_chart(curve, width=65, height=14):
    if len(curve) < 2: return "Sem dados."
    if len(curve) > width:
        step = len(curve) / width
        s = [curve[int(i * step)] for i in range(width)]
    else:
        s = curve
    mn, mx = min(s), max(s)
    rng = mx - mn if mx != mn else 1
    lines = []
    for row in range(height, -1, -1):
        val = mn + (rng * row / height)
        label = f"${val:>8.2f} │"
        chars = []
        for v in s:
            level = int((v - mn) / rng * height)
            if level == row: chars.append("█")
            elif level > row: chars.append("│")
            else: chars.append(" ")
        lines.append(label + "".join(chars))
    lines.append("           └" + "─" * len(s))
    lines.append("            " + "Início" + " " * max(0, len(s) - 10) + "Fim")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# EXECUÇÃO
# ══════════════════════════════════════════════════════════════════════

def run_backtest():
    print("\n" + "═" * 60)
    print("  🔬 BACKTEST — Trading Bot Binance")
    print(f"  Período: últimos {DIAS_BACKTEST} dias")
    print(f"  Capital: ${CAPITAL_INICIAL:,.2f} | Risco: {RISCO_POR_TRADE*100}%/trade")
    print(f"  Pares: {', '.join(PARES)}")
    print("═" * 60 + "\n")

    engine = BacktestEngine()

    # Fase 1: Buscar dados
    print("📥 Buscando dados históricos da Binance...")
    dados = {}
    for par in PARES:
        print(f"  → {par}...", end=" ", flush=True)
        d1h  = fetch_klines(par, "1h",  DIAS_BACKTEST + 15)
        d4h  = fetch_klines(par, "4h",  DIAS_BACKTEST + 60)
        d15m = fetch_klines(par, "15m", DIAS_BACKTEST + 5)
        if d1h.empty or d4h.empty or d15m.empty:
            print("❌"); continue
        add_indicators(d1h, d4h, d15m)
        dados[par] = {"1h": d1h, "4h": d4h, "15m": d15m}
        print(f"✅ {len(d1h)} candles")

    if not dados:
        print("\n❌ Sem dados. Verifique sua conexão.")
        return

    # Fase 2: Simular
    print(f"\n🔄 Simulando {DIAS_BACKTEST} dias...\n")
    all_ts = sorted(set(ts for dfs in dados.values() for ts in dfs["1h"].index))
    cutoff = all_ts[-1] - pd.Timedelta(days=DIAS_BACKTEST)
    sim_ts = [ts for ts in all_ts if ts >= cutoff]
    sinais = 0

    for ts in sim_ts:
        engine.novo_dia(ts.strftime("%Y-%m-%d"))
        for par, dfs in dados.items():
            d1h = dfs["1h"]
            if ts not in d1h.index: continue
            idx = d1h.index.get_loc(ts)
            if idx < 1: continue
            c, p = d1h.iloc[idx], d1h.iloc[idx - 1]

            m4 = dfs["4h"].index <= ts
            if m4.sum() == 0: continue
            c4h = dfs["4h"][m4].iloc[-1]

            m15 = dfs["15m"].index <= ts
            if m15.sum() == 0: continue
            c15 = dfs["15m"][m15].iloc[-1]

            engine.verificar(par, c["high"], c["low"], ts)

            sinal = check_signal(c, p, c4h, c15, c["close"])
            if sinal:
                sinais += 1
                engine.abrir(par, sinal, ts)

    # Fechar abertas
    for pos in engine.posicoes_abertas[:]:
        if pos["par"] in dados:
            lp = dados[pos["par"]]["1h"]["close"].iloc[-1]
            pnl = ((lp - pos["entry"]) if pos["direcao"] == "LONG" else (pos["entry"] - lp)) * pos["qty"]
            pos.update({"resultado": "ABERTA", "pnl": round(pnl, 4), "timestamp_close": sim_ts[-1]})
            engine.saldo += pnl
            engine.trades_fechados.append(pos)
        engine.posicoes_abertas.remove(pos)
    engine._update_eq()

    # Fase 3: Relatório
    r = engine.relatorio()

    print("═" * 60)
    print("  📊 RESULTADO DO BACKTEST")
    print("═" * 60)
    print(f"\n  📅 Período:           {r['periodo']} dias")
    print(f"  💰 Capital inicial:   ${r['capital_i']:,.2f}")
    print(f"  💎 Capital final:     ${r['capital_f']:,.2f}")
    e = "🟢" if r['pnl'] >= 0 else "🔴"
    print(f"  {e} PnL total:         {'+' if r['pnl']>=0 else ''}{r['pnl']:,.2f} USDT ({r['ret']:+.2f}%)")
    print(f"\n  📈 Total trades:      {r['total']}")
    print(f"  ✅ Wins:              {r['wins']}   ({r['wr']}%)")
    print(f"  ❌ Losses:            {r['losses']}")
    print(f"  📊 Profit Factor:     {r['pf']:.2f}")
    print(f"  💵 Média win:         ${r['aw']:,.2f}")
    print(f"  💸 Média loss:        ${r['al']:,.2f}")
    print(f"  📉 Max drawdown:      {r['mdd']:.2f}%")
    print(f"  🔥 Melhor sequência:  {r['msw']} wins")
    print(f"  ❄️  Pior sequência:    {r['msl']} losses")
    print(f"  🔄 Sinais gerados:    {sinais}")
    print(f"\n  LONG:  {r['longs']} | SHORT: {r['shorts']}")

    if r["best"]:
        b = r["best"]
        print(f"\n  🏆 Melhor: {b['par']} {b['direcao']} → {b['resultado']} | +{b['pnl']:,.2f}")
    if r["worst"]:
        w = r["worst"]
        print(f"  💀 Pior:   {w['par']} {w['direcao']} → {w['resultado']} | {w['pnl']:,.2f}")

    print("\n  ── Por Par ───────────────────────────────────────")
    for par, d in sorted(r["by_pair"].items(), key=lambda x: x[1]["pnl"], reverse=True):
        wr2 = (d["wins"]/d["trades"]*100) if d["trades"] > 0 else 0
        em = "🟢" if d["pnl"] >= 0 else "🔴"
        print(f"  {em} {par:>10s}  {d['trades']:>3d} trades  WR:{wr2:>5.1f}%  PnL:{d['pnl']:>+9.2f}")

    print("\n  ── Equity Curve ──────────────────────────────────")
    print(ascii_chart(r["equity"]))

    # Salvar JSON
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_result.json")
    save = {k: v for k, v in r.items() if k not in ("trades", "equity")}
    serialized_trades = []
    for t in r["trades"]:
        st = {}
        for k, v in t.items():
            st[k] = str(v) if "timestamp" in k else v
        serialized_trades.append(st)
    save["trades"] = serialized_trades
    save["equity"] = r["equity"]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(save, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  📁 Detalhes salvos em: backtest_result.json")

    print("\n" + "═" * 60)
    if r["wr"] >= 45 and r["pf"] >= 1.2:
        print("  ✅ VEREDICTO: Bot APROVADO para Testnet")
    elif r["wr"] >= 35:
        print("  ⚠️  VEREDICTO: Resultados medianos — ajuste estratégia")
    else:
        print("  ❌ VEREDICTO: Bot REPROVADO — revise parâmetros")
    print("═" * 60 + "\n")
    return r


if __name__ == "__main__":
    run_backtest()
