"""
bot.py — Lógica principal do bot de trading.

Ciclo principal:
  1. Verificar drawdown diário → pausar se atingido.
  2. Monitorar posições abertas (SL/TP executados?).
  3. Se pode abrir novas posições → escanear mercado.
  4. Validar oportunidades contra todas as regras de risco.
  5. Executar ordens aprovadas.
  6. Dormir até o próximo ciclo (5 min padrão).
"""

import time
from datetime import datetime, timezone

from binance.client import Client

from config import (
    API_KEY,
    API_SECRET,
    TESTNET,
    CAPITAL,
    DRAWDOWN_MAX,
    MAX_POSICOES,
    PARES_TIER1,
    PARES_TIER2,
    INTERVALO_CICLO_SEGUNDOS,
    INTERVALO_PAUSA_DRAWDOWN,
    INTERVALO_RETRY_ERRO,
)
from risk_manager import RiskManager
from order_manager import OrderManager
from scanner import Scanner
from logger import Logger


class TradingBot:
    """Bot de trading automatizado para Binance com gestão de risco rigorosa."""

    def __init__(self):
        # ── Conexão com a Binance ─────────────────────────────────────────
        try:
            self.client = Client(API_KEY, API_SECRET, testnet=TESTNET)
            self._client_error = None
        except Exception as e:
            self.client = None
            self._client_error = e
            self.logger = Logger()
            self.logger.error(f"🛑 Erro ao conectar na Binance: {e}")
            self.logger.error("   Se você está no Railway, seu servidor pode estar nos EUA (IP bloqueado).")
            self.logger.error("   Para corrigir: Mude a região do seu serviço Railway para Europa (EU).")

        # ── Módulos ───────────────────────────────────────────────────────
        if self.client:
            self.risk   = RiskManager(self.client)
            self.orders = OrderManager(self.client)
            self.scanner = Scanner(self.client)
            self.logger = Logger()
        else:
            self.risk = None
            self.orders = None
            self.scanner = None

        # ── Estado interno ────────────────────────────────────────────────
        self.posicoes_abertas: list[dict] = []
        self.pnl_dia: float = 0.0
        self.trades_dia: int = 0
        self.wins_dia: int = 0
        self.rodando: bool = True
        self.dia_atual: str = ""
        self.ciclos: int = 0

    # ── LOOP PRINCIPAL ────────────────────────────────────────────────────

    def run(self):
        """Loop principal do bot — roda 24/7 com tratamento de erros."""
        from config import CREDENCIAIS_OK
        
        if not CREDENCIAIS_OK:
            self.logger.error("🛑 Chaves da API da Binance não configuradas no ambiente!")
            self.logger.error("   O dashboard está online, mas o bot ficará em repouso absoluto.\n")
            while self.rodando:
                time.sleep(10)
            return

        if self.client is None:
            self.logger.error(f"🛑 Erro ao conectar na Binance: {self._client_error}")
            self.logger.error("   O dashboard está online, mas o bot NÃO OPERARÁ (Falha na Binance).")
            while self.rodando:
                time.sleep(10)
            return
        modo = "TESTNET" if TESTNET else "⚠️  PRODUÇÃO"
        self.logger.info(f"🚀 Bot iniciado | Modo: {modo} | Capital: ${CAPITAL}")
        self.logger.info(
            f"   Risco/trade: {CAPITAL * 0.01:.2f} USDT | "
            f"Max posições: {MAX_POSICOES} | "
            f"Drawdown max: {DRAWDOWN_MAX * 100:.0f}%"
        )

        while self.rodando:
            try:
                self.ciclos += 1
                self._atualizar_dia()

                # 1. Verificar drawdown diário
                if not self.risk.verificar_drawdown(self.pnl_dia, CAPITAL):
                    self.logger.warning(
                        f"🛑 DRAWDOWN DIÁRIO ATINGIDO ({self.pnl_dia:+.2f} USDT). "
                        f"Pausando por {INTERVALO_PAUSA_DRAWDOWN // 60} min."
                    )
                    time.sleep(INTERVALO_PAUSA_DRAWDOWN)
                    continue

                # 2. Monitorar posições abertas
                self._monitorar_posicoes()

                # 3. Buscar novas oportunidades se houver slot
                if len(self.posicoes_abertas) < MAX_POSICOES:
                    pares = PARES_TIER1 + PARES_TIER2
                    oportunidades = self.scanner.escanear(pares)

                    # Executar as 2 melhores oportunidades
                    for opp in oportunidades[:2]:
                        if len(self.posicoes_abertas) >= MAX_POSICOES:
                            break
                        self._abrir_posicao(opp)
                else:
                    self.logger.debug(
                        f"Todas as {MAX_POSICOES} posições em uso. "
                        f"Aguardando fechamento."
                    )

                # 4. Log de status periódico (a cada 12 ciclos ≈ 1h)
                if self.ciclos % 12 == 0:
                    self._log_status()

                time.sleep(INTERVALO_CICLO_SEGUNDOS)

            except KeyboardInterrupt:
                self.logger.info("⏹️  Bot encerrado pelo usuário.")
                self.rodando = False
            except Exception as e:
                self.logger.error(f"Erro no loop principal: {e}")
                time.sleep(INTERVALO_RETRY_ERRO)

        # Resumo do dia ao encerrar
        self.logger.resumo_diario(self.pnl_dia, self.trades_dia, self.wins_dia)

    # ── ABERTURA DE POSIÇÃO ───────────────────────────────────────────────

    def _abrir_posicao(self, opp: dict):
        """Valida todas as regras de risco e abre posição se aprovada."""
        saldo = self.risk.get_saldo_usdt()

        # Validação completa ANTES de qualquer ordem
        pode, motivo = self.risk.validar_trade(
            saldo=saldo,
            entry=opp["entry"],
            sl=opp["sl"],
            tp=opp["tp"],
            direcao=opp["direcao"],
            posicoes_abertas=len(self.posicoes_abertas),
            pnl_dia=self.pnl_dia,
            capital=CAPITAL,
        )
        if not pode:
            self.logger.info(
                f"⛔ Trade rejeitado ({opp['par']} {opp['direcao']}): {motivo}"
            )
            return

        # Calcular tamanho da posição
        tamanho = self.risk.calcular_tamanho(saldo, opp["entry"], opp["sl"])
        if tamanho <= 0:
            self.logger.info(
                f"⛔ Tamanho calculado = 0 para {opp['par']}. Pulando."
            )
            return

        # Executar ordem
        ordem = self.orders.abrir_ordem(
            par=opp["par"],
            direcao=opp["direcao"],
            quantidade=tamanho,
            entry=opp["entry"],
            sl=opp["sl"],
            tp=opp["tp"],
        )

        if ordem:
            posicao = {
                **opp,
                "ordem_id": ordem["orderId"],
                "quantidade": tamanho,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.posicoes_abertas.append(posicao)
            self.logger.trade_aberto(opp, tamanho)

    # ── MONITORAMENTO DE POSIÇÕES ─────────────────────────────────────────

    def _monitorar_posicoes(self):
        """Verifica status de cada posição aberta e contabiliza PnL."""
        for pos in self.posicoes_abertas[:]:  # cópia para iterar com segurança
            status = self.orders.verificar_status(pos["par"], pos["ordem_id"])

            if status == "FILLED":
                # A ordem principal foi preenchida — monitorar SL/TP
                # (O OCO cuida do fechamento automaticamente)
                pass

            elif status in ("CANCELED", "EXPIRED", "REJECTED"):
                self.logger.info(
                    f"Ordem {pos['ordem_id']} ({pos['par']}) status: {status}. "
                    f"Removendo da lista."
                )
                self.posicoes_abertas.remove(pos)

            elif status == "UNKNOWN":
                self.logger.warning(
                    f"Status desconhecido para {pos['par']} #{pos['ordem_id']}"
                )

            # Verificar se o OCO foi executado (SL ou TP atingido)
            try:
                open_orders = self.client.get_open_orders(symbol=pos["par"])
                oco_ativas = [
                    o for o in open_orders
                    if o.get("side") == (
                        "SELL" if pos["direcao"] == "LONG" else "BUY"
                    )
                ]
                # Se não há mais ordens OCO abertas e a posição foi preenchida,
                # significa que SL ou TP foram executados
                if status == "FILLED" and len(oco_ativas) == 0:
                    pnl = self.orders.calcular_pnl(pos)
                    self.pnl_dia += pnl
                    self.trades_dia += 1
                    if pnl >= 0:
                        self.wins_dia += 1
                    self.logger.trade_fechado(pos, pnl)
                    self.posicoes_abertas.remove(pos)
            except Exception as e:
                self.logger.error(
                    f"Erro ao verificar OCO {pos['par']}: {e}"
                )

    # ── UTILITÁRIOS ───────────────────────────────────────────────────────

    def _atualizar_dia(self):
        """Reseta contadores ao virar o dia (UTC)."""
        hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if hoje != self.dia_atual:
            if self.dia_atual:
                self.logger.resumo_diario(
                    self.pnl_dia, self.trades_dia, self.wins_dia
                )
            self.dia_atual = hoje
            self.pnl_dia = 0.0
            self.trades_dia = 0
            self.wins_dia = 0
            self.logger.info(f"📅 Novo dia: {hoje}")

    def _log_status(self):
        """Log periódico com estado atual do bot."""
        try:
            saldo = self.risk.get_saldo_usdt()
        except Exception:
            saldo = 0.0

        self.logger.info(
            f"📊 Status | Posições: {len(self.posicoes_abertas)}/{MAX_POSICOES} | "
            f"PnL dia: {self.pnl_dia:+.2f} USDT | "
            f"Trades: {self.trades_dia} | "
            f"Saldo: {saldo:.2f} USDT | "
            f"Ciclo #{self.ciclos}"
        )
