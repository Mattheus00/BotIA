"""
logger.py — Sistema de logs estruturados e relatórios de trade.

Usa loguru para rotação automática de arquivos de log (1 por dia, retém 30 dias).
Todos os eventos de trade são logados em JSON para facilitar análise posterior.
"""

import json
import os
from datetime import datetime, timezone
from loguru import logger


class Logger:
    """Wrapper de logging com métodos específicos para eventos de trading."""

    def __init__(self, log_dir: str = "logs"):
        os.makedirs(log_dir, exist_ok=True)

        # Remove handler padrão do loguru para evitar duplicatas no stdout
        logger.remove()

        # Console — formato legível
        logger.add(
            sink=lambda msg: print(msg, end=""),
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{message}</cyan>"
            ),
            level="INFO",
        )

        # Arquivo — rotação diária, retenção de 30 dias
        logger.add(
            os.path.join(log_dir, "bot_{time}.log"),
            rotation="1 day",
            retention="30 days",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            level="DEBUG",
        )

        # Arquivo separado para trades (facilita backtest / auditoria)
        logger.add(
            os.path.join(log_dir, "trades_{time}.jsonl"),
            rotation="1 day",
            retention="90 days",
            format="{message}",
            level="INFO",
            filter=lambda record: record["extra"].get("is_trade", False),
        )

    # ── Métodos genéricos ─────────────────────────────────────────────────
    def info(self, msg: str):
        logger.info(msg)

    def warning(self, msg: str):
        logger.warning(msg)

    def error(self, msg: str):
        logger.error(msg)

    def debug(self, msg: str):
        logger.debug(msg)

    # ── Eventos de trade ──────────────────────────────────────────────────
    def trade_aberto(self, opp: dict, quantidade: float):
        """Loga abertura de posição em JSON estruturado."""
        data = {
            "evento": "TRADE_ABERTO",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **opp,
            "quantidade": quantidade,
        }
        logger.bind(is_trade=True).info(json.dumps(data, ensure_ascii=False))
        logger.info(
            f"📈 ABERTO {opp['direcao']} {opp['par']} | "
            f"Qty: {quantidade} | Entry: {opp['entry']} | "
            f"SL: {opp['sl']} | TP: {opp['tp']} | "
            f"Conf: {opp['confirmacoes']} | {opp.get('motivo', '')}"
        )

    def trade_fechado(self, posicao: dict, pnl: float):
        """Loga encerramento de posição."""
        emoji = "✅" if pnl >= 0 else "❌"
        data = {
            "evento": "TRADE_FECHADO",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "par": posicao["par"],
            "direcao": posicao["direcao"],
            "pnl_usdt": round(pnl, 4),
        }
        logger.bind(is_trade=True).info(json.dumps(data, ensure_ascii=False))
        logger.info(
            f"{emoji} FECHADO {posicao['par']} | "
            f"PnL: {pnl:+.4f} USDT"
        )

    def resumo_diario(self, pnl_dia: float, total_trades: int, wins: int):
        """Loga resumo do dia."""
        wr = (wins / total_trades * 100) if total_trades > 0 else 0
        data = {
            "evento": "RESUMO_DIARIO",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pnl_dia_usdt": round(pnl_dia, 4),
            "total_trades": total_trades,
            "wins": wins,
            "win_rate": round(wr, 2),
        }
        logger.bind(is_trade=True).info(json.dumps(data, ensure_ascii=False))
        logger.info(
            f"📊 RESUMO DIA | PnL: {pnl_dia:+.4f} USDT | "
            f"Trades: {total_trades} | WR: {wr:.1f}%"
        )
