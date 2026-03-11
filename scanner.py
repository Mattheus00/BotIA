"""
scanner.py — Scanner de oportunidades de mercado.

Varre pares configurados e retorna oportunidades ordenadas por força do sinal.
Também identifica top movers por volume para descoberta de novos setups.
"""

from binance.client import Client

from strategy import analisar_par
from logger import Logger


class Scanner:
    """Escaneia o mercado buscando setups com múltiplas confirmações."""

    def __init__(self, client: Client):
        self.client = client
        self.logger = Logger()

    def escanear(self, pares: list[str]) -> list[dict]:
        """
        Analisa todos os pares e retorna lista de oportunidades
        ordenadas por número de confirmações (mais forte primeiro).
        """
        resultados = []

        for par in pares:
            try:
                sinal = analisar_par(self.client, par)
                if sinal:
                    self.logger.info(
                        f"🎯 Sinal encontrado: {sinal['direcao']} {par} "
                        f"({sinal['confirmacoes']} conf.) — {sinal['motivo']}"
                    )
                    resultados.append(sinal)
            except Exception as e:
                self.logger.error(f"Erro ao analisar {par}: {e}")

        # Ordena por confirmações (mais forte primeiro)
        resultados.sort(key=lambda x: x["confirmacoes"], reverse=True)

        if resultados:
            self.logger.info(
                f"📡 Scan completo: {len(resultados)} oportunidade(s) "
                f"em {len(pares)} pares analisados."
            )
        else:
            self.logger.debug(
                f"📡 Scan completo: nenhuma oportunidade em {len(pares)} pares."
            )

        return resultados

    def top_movers(self, limite: int = 10) -> list[dict]:
        """
        Retorna os pares USDT com maior variação de preço nas últimas 24h,
        filtrados por volume mínimo de $10M.

        Útil para descobrir pares com momentum que podem gerar setups.
        """
        try:
            tickers = self.client.get_ticker()
            # Filtrar apenas pares USDT com volume relevante
            usdt_pairs = [
                t for t in tickers
                if t["symbol"].endswith("USDT")
                and float(t["quoteVolume"]) > 10_000_000
            ]
            # Ordenar por variação percentual
            movers = sorted(
                usdt_pairs,
                key=lambda x: abs(float(x["priceChangePercent"])),
                reverse=True,
            )[:limite]

            self.logger.info(
                f"🔥 Top {len(movers)} movers: "
                + ", ".join(
                    f"{m['symbol']} ({float(m['priceChangePercent']):+.1f}%)"
                    for m in movers[:5]
                )
            )
            return movers

        except Exception as e:
            self.logger.error(f"Erro ao buscar top movers: {e}")
            return []
