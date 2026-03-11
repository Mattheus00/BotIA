"""
main.py — Entry point do bot de trading.

Uso:
    python main.py

Inicia o servidor API (Flask) na porta 5000 e aguarda o comando
de START via dashboard ou chamada direta à API.

Certifique-se de:
  1. Configurar o .env com suas credenciais da Binance.
  2. Começar com MODO_TESTNET=true.
  3. Instalar dependências: pip install -r requirements.txt
"""

import os
import sys


def main():
    port = int(os.environ.get("PORT", 5000))
    print(
        "\n"
        "╔══════════════════════════════════════════════════╗\n"
        "║         🤖 TRADING BOT — BINANCE                ║\n"
        "║         Gestão de risco automatizada             ║\n"
        "║                                                  ║\n"
       f"║   API:       http://0.0.0.0:{port:<20s}  ║\n"
        "╚══════════════════════════════════════════════════╝\n"
    )

    try:
        from bot import TradingBot
        from api import set_bot, run_api

        # Criar instância do bot (não inicia automaticamente)
        bot = TradingBot()
        bot.rodando = False  # Aguarda comando do dashboard

        # Registrar bot na API
        set_bot(bot)

        print("✅ Bot pronto. Aguardando comando de START via dashboard...")
        print(f"   → Acesse o dashboard no navegador\n")

        # Iniciar servidor API (bloqueia aqui)
        run_api(host="0.0.0.0", port=port)

    except ValueError as e:
        # Erros de configuração (config.py validations)
        print(f"\n❌ Erro de configuração: {e}")
        print("   → Verifique seu arquivo .env\n")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⏹️  Servidor encerrado pelo usuário.")
        sys.exit(0)

    except Exception as e:
        print(f"\n💥 Erro fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
