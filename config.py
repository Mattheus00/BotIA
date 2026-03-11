"""
config.py — Configurações centrais do bot de trading.

Carrega variáveis de ambiente do .env e define constantes globais.
Nunca commitar o .env com credenciais reais.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── CREDENCIAIS ──────────────────────────────────────────────────────────────
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TESTNET = os.getenv("MODO_TESTNET", "true").lower() == "true"

# ── PARÂMETROS DE RISCO ──────────────────────────────────────────────────────
CAPITAL = float(os.getenv("CAPITAL_INICIAL", 1000))
RISCO_POR_TRADE = float(os.getenv("RISCO_POR_TRADE", 0.01))       # 1% por trade
MAX_POSICOES = int(os.getenv("MAX_POSICOES", 5))
DRAWDOWN_MAX = float(os.getenv("DRAWDOWN_DIARIO_MAX", 0.03))      # 3% drawdown diário
ALAVANCAGEM = int(os.getenv("ALAVANCAGEM", 1))                    # 1 = sem alavancagem
MIN_RR_RATIO = 3.0                                                 # Risk/Reward mínimo 1:3
MIN_CONFIRMACOES = 3.5                                              # Mínimo de confirmações

# ── PARÂMETROS DE ATR ────────────────────────────────────────────────────────
ATR_MULTIPLIER = 2.0            # SL = entry ± (ATR * multiplicador)
ATR_VOL_MAX = 0.03              # ATR > 3% do preço = volátil demais
ATR_VOL_MIN = 0.001             # ATR < 0.1% do preço = parado demais

# ── PARES POR PRIORIDADE ─────────────────────────────────────────────────────
PARES_TIER1 = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
PARES_TIER2 = ["SOLUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT"]
PARES_SCAN  = ["LINKUSDT", "DOTUSDT", "ARBUSDT", "OPUSDT", "NEARUSDT", "ATOMUSDT"]

# ── TIMEFRAMES ────────────────────────────────────────────────────────────────
TF_PRINCIPAL    = "1h"
TF_CONFIRMACAO  = "15m"
TF_TENDENCIA    = "4h"

# ── CICLO DO BOT ──────────────────────────────────────────────────────────────
INTERVALO_CICLO_SEGUNDOS = 300          # 5 minutos entre cada ciclo
INTERVALO_PAUSA_DRAWDOWN = 3600         # 1 hora de pausa após drawdown
INTERVALO_RETRY_ERRO = 60              # Retry após erro

# ── LIMITES DE POSIÇÃO ────────────────────────────────────────────────────────
MAX_PCT_SALDO_POR_POSICAO = 0.20       # Nunca mais de 20% do saldo numa posição
MAX_ALAVANCAGEM = 3                     # Teto absoluto de alavancagem

# ── VALIDAÇÕES NA INICIALIZAÇÃO ───────────────────────────────────────────────
import logging as _logging

CREDENCIAIS_OK = True

if not API_KEY or API_KEY == "sua_api_key_aqui":
    _logging.warning(
        "⚠️  BINANCE_API_KEY não configurada! "
        "O dashboard funcionará, mas o bot não pode operar."
    )
    CREDENCIAIS_OK = False

if not API_SECRET or API_SECRET == "sua_api_secret_aqui":
    _logging.warning(
        "⚠️  BINANCE_API_SECRET não configurada! "
        "O dashboard funcionará, mas o bot não pode operar."
    )
    CREDENCIAIS_OK = False

if ALAVANCAGEM > MAX_ALAVANCAGEM:
    raise ValueError(
        f"⚠️  Alavancagem {ALAVANCAGEM}x excede o máximo permitido ({MAX_ALAVANCAGEM}x)."
    )
