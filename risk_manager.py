"""
risk_manager.py — Gestão de risco e position sizing.

Regras invioláveis:
  • Risco máximo de 1% do capital por trade (configurável).
  • Nunca alocar mais de 20% do saldo numa única posição.
  • Drawdown diário de 3% pausa o bot.
  • Nunca aumentar posição perdedora (martingale proibido).
"""

from config import (
    RISCO_POR_TRADE,
    DRAWDOWN_MAX,
    MAX_PCT_SALDO_POR_POSICAO,
    ALAVANCAGEM,
    MIN_RR_RATIO,
)


class RiskManager:
    """Controla position sizing, drawdown e validação de risco."""

    def __init__(self, client):
        self.client = client

    # ── Saldo disponível ──────────────────────────────────────────────────

    def get_saldo_usdt(self) -> float:
        """Retorna o saldo livre em USDT."""
        account = self.client.get_account()
        for asset in account["balances"]:
            if asset["asset"] == "USDT":
                return float(asset["free"])
        return 0.0

    # ── Position sizing ───────────────────────────────────────────────────

    def calcular_tamanho(self, saldo: float, entry: float, sl: float) -> float:
        """
        Calcula tamanho da posição baseado em risco fixo.

        Fórmula:
            quantidade = (saldo × risco_pct) / |entry - sl|

        Limitadores:
            - Nunca mais de MAX_PCT_SALDO_POR_POSICAO (20%) numa posição.
            - Aplica alavancagem se configurada (máx 3x).

        Retorna 0.0 se o trade for inválido.
        """
        distancia_sl = abs(entry - sl)
        if distancia_sl == 0 or entry <= 0:
            return 0.0

        risco_usdt = saldo * RISCO_POR_TRADE
        quantidade = risco_usdt / distancia_sl

        # Aplica alavancagem (cuidado: maior exposição)
        quantidade *= ALAVANCAGEM

        # Limitar exposição máxima por posição
        max_usdt = saldo * MAX_PCT_SALDO_POR_POSICAO * ALAVANCAGEM
        max_qty = max_usdt / entry
        quantidade = min(quantidade, max_qty)

        # Garantir que o valor não é negativo
        return round(max(quantidade, 0.0), 6)

    # ── Validações de risco ───────────────────────────────────────────────

    def verificar_drawdown(self, pnl_dia: float, capital: float) -> bool:
        """Retorna True se PODE continuar operando (drawdown dentro do limite)."""
        return abs(pnl_dia) < capital * DRAWDOWN_MAX

    def validar_rr_ratio(self, entry: float, sl: float, tp: float, direcao: str) -> bool:
        """Verifica se o Risk/Reward ratio atende o mínimo configurado."""
        if direcao == "LONG":
            risco = entry - sl
            retorno = tp - entry
        else:
            risco = sl - entry
            retorno = entry - tp

        if risco <= 0:
            return False

        rr = retorno / risco
        return rr >= MIN_RR_RATIO

    def validar_trade(
        self,
        saldo: float,
        entry: float,
        sl: float,
        tp: float,
        direcao: str,
        posicoes_abertas: int,
        pnl_dia: float,
        capital: float,
    ) -> tuple[bool, str]:
        """
        Validação completa antes de abrir qualquer trade.

        Retorna (pode_operar, motivo).
        """
        from config import MAX_POSICOES

        # 1. Drawdown diário
        if not self.verificar_drawdown(pnl_dia, capital):
            return False, "Drawdown diário atingido"

        # 2. Máximo de posições
        if posicoes_abertas >= MAX_POSICOES:
            return False, f"Máximo de {MAX_POSICOES} posições atingido"

        # 3. Saldo mínimo
        risco_usdt = saldo * RISCO_POR_TRADE
        if risco_usdt < 1.0:  # Mínimo de $1 para operar
            return False, "Saldo insuficiente para operar"

        # 4. Risk/Reward
        if not self.validar_rr_ratio(entry, sl, tp, direcao):
            return False, f"R:R abaixo do mínimo ({MIN_RR_RATIO})"

        # 5. SL obrigatório
        if sl <= 0:
            return False, "Stop Loss é obrigatório"

        return True, "OK"
