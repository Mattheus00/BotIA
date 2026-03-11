"""
order_manager.py — Execução de ordens na Binance.

Responsável por:
  • Abrir ordens LIMIT com SL/TP via OCO.
  • Verificar status de ordens.
  • Calcular PnL realizado.
  • Ajustar precisão de preço e quantidade conforme regras do par.
"""

from binance.client import Client
from binance.enums import (
    SIDE_BUY,
    SIDE_SELL,
    ORDER_TYPE_LIMIT,
    TIME_IN_FORCE_GTC,
)

from logger import Logger


class OrderManager:
    """Gerencia execução de ordens na Binance."""

    def __init__(self, client: Client):
        self.client = client
        self.logger = Logger()
        self._symbol_info_cache: dict = {}

    # ── Informações do par ────────────────────────────────────────────────

    def _get_symbol_info(self, par: str) -> dict:
        """Cache das regras de precisão do par."""
        if par not in self._symbol_info_cache:
            info = self.client.get_symbol_info(par)
            self._symbol_info_cache[par] = info
        return self._symbol_info_cache[par]

    def _ajustar_quantidade(self, par: str, quantidade: float) -> float:
        """Ajusta a quantidade para a precisão exigida pelo par."""
        info = self._get_symbol_info(par)
        if not info:
            return round(quantidade, 6)

        for f in info.get("filters", []):
            if f["filterType"] == "LOT_SIZE":
                step = float(f["stepSize"])
                if step > 0:
                    precision = len(str(step).rstrip("0").split(".")[-1])
                    quantidade = round(quantidade - (quantidade % step), precision)
                min_qty = float(f["minQty"])
                if quantidade < min_qty:
                    return 0.0
                break
        return quantidade

    def _ajustar_preco(self, par: str, preco: float) -> str:
        """Ajusta o preço para a precisão exigida pelo par."""
        info = self._get_symbol_info(par)
        if not info:
            return str(round(preco, 2))

        for f in info.get("filters", []):
            if f["filterType"] == "PRICE_FILTER":
                tick = float(f["tickSize"])
                if tick > 0:
                    precision = len(str(tick).rstrip("0").split(".")[-1])
                    preco = round(preco - (preco % tick), precision)
                break
        return str(preco)

    # ── Abertura de ordens ────────────────────────────────────────────────

    def abrir_ordem(
        self,
        par: str,
        direcao: str,
        quantidade: float,
        entry: float,
        sl: float,
        tp: float,
    ) -> dict | None:
        """
        Abre ordem LIMIT + OCO (SL e TP) na Binance.

        Retorna dict da ordem principal ou None se falhar.
        """
        try:
            # Ajustar precisão
            quantidade = self._ajustar_quantidade(par, quantidade)
            if quantidade <= 0:
                self.logger.warning(
                    f"Quantidade {quantidade} inválida para {par} após ajuste."
                )
                return None

            entry_str = self._ajustar_preco(par, entry)
            tp_str    = self._ajustar_preco(par, tp)
            sl_str    = self._ajustar_preco(par, sl)

            # Stop limit price com margem de 0.1% para garantir execução
            if direcao == "LONG":
                sl_limit = sl * 0.999
            else:
                sl_limit = sl * 1.001
            sl_limit_str = self._ajustar_preco(par, sl_limit)

            side = SIDE_BUY if direcao == "LONG" else SIDE_SELL

            # 1. Ordem principal (LIMIT)
            ordem = self.client.create_order(
                symbol=par,
                side=side,
                type=ORDER_TYPE_LIMIT,
                timeInForce=TIME_IN_FORCE_GTC,
                quantity=quantidade,
                price=entry_str,
            )

            # 2. OCO para SL + TP
            sl_side = SIDE_SELL if direcao == "LONG" else SIDE_BUY
            try:
                self.client.create_oco_order(
                    symbol=par,
                    side=sl_side,
                    quantity=quantidade,
                    price=tp_str,
                    stopPrice=sl_str,
                    stopLimitPrice=sl_limit_str,
                    stopLimitTimeInForce=TIME_IN_FORCE_GTC,
                )
            except Exception as e:
                self.logger.error(
                    f"⚠️ Ordem principal aberta mas OCO falhou para {par}: {e}. "
                    f"CANCELE A ORDEM {ordem['orderId']} MANUALMENTE se necessário!"
                )

            self.logger.info(
                f"Ordem {ordem['orderId']} criada: {direcao} {par} "
                f"qty={quantidade} entry={entry_str} sl={sl_str} tp={tp_str}"
            )
            return ordem

        except Exception as e:
            self.logger.error(f"Erro ao abrir ordem {par}: {e}")
            return None

    # ── Status e PnL ──────────────────────────────────────────────────────

    def verificar_status(self, par: str, ordem_id: int) -> str:
        """Retorna o status da ordem (NEW, FILLED, CANCELED, etc.)."""
        try:
            ordem = self.client.get_order(symbol=par, orderId=ordem_id)
            return ordem["status"]
        except Exception as e:
            self.logger.error(f"Erro ao verificar status {par} #{ordem_id}: {e}")
            return "UNKNOWN"

    def calcular_pnl(self, posicao: dict) -> float:
        """Calcula PnL realizado baseado nos trades recentes."""
        try:
            trades = self.client.get_my_trades(
                symbol=posicao["par"], limit=10
            )
            if not trades:
                return 0.0

            # Buscar trades relacionados à posição
            ultimo = trades[-1]
            preco_saida = float(ultimo["price"])
            qty = float(ultimo["qty"])
            comissao = float(ultimo.get("commission", 0))

            if posicao["direcao"] == "LONG":
                pnl = (preco_saida - posicao["entry"]) * qty
            else:
                pnl = (posicao["entry"] - preco_saida) * qty

            # Descontar comissão (se em USDT)
            pnl -= comissao
            return round(pnl, 4)

        except Exception as e:
            self.logger.error(f"Erro ao calcular PnL {posicao['par']}: {e}")
            return 0.0

    def cancelar_ordens_abertas(self, par: str):
        """Cancela todas as ordens abertas de um par."""
        try:
            ordens = self.client.get_open_orders(symbol=par)
            for ordem in ordens:
                self.client.cancel_order(
                    symbol=par, orderId=ordem["orderId"]
                )
                self.logger.info(
                    f"Ordem {ordem['orderId']} cancelada para {par}"
                )
        except Exception as e:
            self.logger.error(f"Erro ao cancelar ordens {par}: {e}")
