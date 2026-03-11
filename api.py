"""
api.py — API REST para controle do bot via dashboard.

Endpoints:
  GET  /api/status  → Estado atual do bot (online, posições, PnL, etc.)
  POST /api/start   → Inicia o bot em thread separada
  POST /api/stop    → Para o bot graciosamente
"""

from flask import Flask, jsonify
from flask_cors import CORS
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)  # Permite chamadas do dashboard (localhost:5173 → localhost:5000)

# Referência global ao bot — será definida pelo main.py
_bot_instance = None
_bot_thread = None


def set_bot(bot, thread=None):
    """Registra a instância do bot para acesso via API."""
    global _bot_instance, _bot_thread
    _bot_instance = bot
    _bot_thread = thread


@app.route("/api/status", methods=["GET"])
def get_status():
    """Retorna o estado completo do bot."""
    if _bot_instance is None:
        return jsonify({
            "online": False,
            "rodando": False,
            "modo": "DESCONECTADO",
            "posicoes_abertas": 0,
            "pnl_dia": 0.0,
            "trades_dia": 0,
            "wins_dia": 0,
            "ciclos": 0,
            "saldo": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    bot = _bot_instance

    # Tentar obter saldo
    saldo = 0.0
    try:
        saldo = bot.risk.get_saldo_usdt()
    except Exception:
        pass

    from config import TESTNET

    return jsonify({
        "online": bot.rodando,
        "rodando": bot.rodando,
        "modo": "TESTNET" if TESTNET else "PRODUÇÃO",
        "posicoes_abertas": len(bot.posicoes_abertas),
        "posicoes": [
            {
                "par": p["par"],
                "direcao": p["direcao"],
                "entry": p["entry"],
                "sl": p["sl"],
                "tp": p["tp"],
                "confirmacoes": p["confirmacoes"],
                "quantidade": p["quantidade"],
                "timestamp": p.get("timestamp", ""),
            }
            for p in bot.posicoes_abertas
        ],
        "pnl_dia": round(bot.pnl_dia, 4),
        "trades_dia": bot.trades_dia,
        "wins_dia": bot.wins_dia,
        "ciclos": bot.ciclos,
        "saldo": round(saldo, 2),
        "dia_atual": bot.dia_atual,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/start", methods=["POST"])
def start_bot():
    """Inicia o bot."""
    import threading

    if _bot_instance is None:
        return jsonify({"success": False, "message": "Bot não inicializado"}), 500

    bot = _bot_instance

    if bot.rodando and _bot_thread and _bot_thread.is_alive():
        return jsonify({"success": False, "message": "Bot já está rodando"}), 400

    bot.rodando = True

    global _bot_thread
    _bot_thread = threading.Thread(target=bot.run, daemon=True, name="trading-bot")
    _bot_thread.start()

    return jsonify({"success": True, "message": "Bot iniciado com sucesso"})


@app.route("/api/stop", methods=["POST"])
def stop_bot():
    """Para o bot graciosamente."""
    if _bot_instance is None:
        return jsonify({"success": False, "message": "Bot não inicializado"}), 500

    bot = _bot_instance

    if not bot.rodando:
        return jsonify({"success": False, "message": "Bot já está parado"}), 400

    bot.rodando = False
    return jsonify({"success": True, "message": "Bot parado com sucesso"})


def run_api(host="0.0.0.0", port=5000):
    """Inicia o servidor Flask."""
    app.run(host=host, port=port, debug=False, use_reloader=False)
