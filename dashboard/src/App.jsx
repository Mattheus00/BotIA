import { useState, useEffect, useCallback, useRef } from 'react'
import './App.css'

/* ═══════════════════════════════════════════════════════════════════
   TRADING BOT DASHBOARD
   Real-time monitoring interface for the Binance trading bot.
   Uses demo data for standalone mode — connect to bot API for live data.
   ═══════════════════════════════════════════════════════════════════ */

// ── Demo data ────────────────────────────────────────────────────────
const DEMO_POSITIONS = [
  {
    par: 'BTCUSDT', direcao: 'LONG', entry: 67234.50, sl: 66480.00,
    tp: 68742.00, confirmacoes: 4.5, motivo: 'RSI=32 | EMA9x21↑ | Preço>EMA50 | MACD_cross↑ | Vol=1.8x',
    quantidade: 0.0045, timestamp: '2026-03-11T14:23:00Z', pnl: 128.45
  },
  {
    par: 'ETHUSDT', direcao: 'LONG', entry: 3456.20, sl: 3390.00,
    tp: 3588.60, confirmacoes: 3.5, motivo: 'RSI=34 | EMA9x21↑ | Preço>EMA50 | ADX=28',
    quantidade: 0.82, timestamp: '2026-03-11T15:10:00Z', pnl: -12.30
  },
  {
    par: 'SOLUSDT', direcao: 'SHORT', entry: 142.80, sl: 146.50,
    tp: 135.40, confirmacoes: 3.0, motivo: 'RSI=72 | EMA9x21↓ | Preço<EMA50',
    quantidade: 4.2, timestamp: '2026-03-11T15:45:00Z', pnl: 34.86
  },
]

const INITIAL_LOGS = [
  { time: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), level: 'info', msg: 'Aguardando inicialização do painel...' }
]

const DEMO_PAIRS = [
  { symbol: 'BTCUSDT', change: '+2.34', vol: '4.2B' },
  { symbol: 'ETHUSDT', change: '+1.85', vol: '2.1B' },
  { symbol: 'BNBUSDT', change: '-0.42', vol: '890M' },
  { symbol: 'SOLUSDT', change: '-1.23', vol: '1.3B' },
  { symbol: 'XRPUSDT', change: '+0.67', vol: '1.8B' },
  { symbol: 'ADAUSDT', change: '+3.12', vol: '650M' },
  { symbol: 'AVAXUSDT', change: '-0.89', vol: '420M' },
  { symbol: 'LINKUSDT', change: '+4.56', vol: '380M' },
  { symbol: 'DOTUSDT', change: '+1.02', vol: '310M' },
  { symbol: 'ARBUSDT', change: '-2.10', vol: '280M' },
]

// Em produção, API e dashboard estão no mesmo servidor (URL relativa)
// Em dev (Vite), usa localhost:5000
const API_URL = import.meta.env.DEV ? 'http://localhost:5000' : ''

// ── Power Icon SVG ───────────────────────────────────────────────────
function PowerIcon() {
  return (
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path className="power-icon" d="M12 3v9" />
      <path className="power-icon" d="M18.36 6.64A9 9 0 1 1 5.64 6.64" />
    </svg>
  )
}

// ── App ──────────────────────────────────────────────────────────────
function App() {
  const [currentTime, setCurrentTime] = useState(new Date())
  const [isTestnet] = useState(true)
  const [botOnline, setBotOnline] = useState(false)
  const [botLoading, setBotLoading] = useState(false)
  const [apiConnected, setApiConnected] = useState(false)
  const [botStatus, setBotStatus] = useState(null)
  const [logs, setLogs] = useState(INITIAL_LOGS)
  const statusInterval = useRef(null)

  // Update clock every second
  useEffect(() => {
    const interval = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(interval)
  }, [])

  // Poll bot status every 3 seconds
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/status`)
      if (res.ok) {
        const data = await res.json()
        setBotOnline(data.rodando)
        setBotStatus(data)
        if (!apiConnected) {
          setLogs(prev => [{ time: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), level: 'info', msg: '✅ Conexão estabelecida com a API!' }, ...prev])
        }
        setApiConnected(true)
      } else {
        setApiConnected(false)
      }
    } catch {
      if (apiConnected) {
        setLogs(prev => [{ time: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), level: 'warning', msg: '⚠️ Conexão perdida com a API!' }, ...prev])
      }
      setApiConnected(false)
      setBotOnline(false)
    }
  }, [apiConnected])

  useEffect(() => {
    fetchStatus()
    statusInterval.current = setInterval(fetchStatus, 3000)
    return () => clearInterval(statusInterval.current)
  }, [fetchStatus])

  // Toggle bot on/off
  const toggleBot = async () => {
    if (botLoading) return
    setBotLoading(true)
    try {
      const endpoint = botOnline ? '/api/stop' : '/api/start'
      const res = await fetch(`${API_URL}${endpoint}`, { method: 'POST' })
      if (res.ok) {
        // Wait a bit then refresh status
        setLogs(prev => [{ time: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), level: 'info', msg: botOnline ? '⏹️ Bot desativado manualmente.' : '🚀 Ordem de inicio enviada ao Bot!' }, ...prev])
        setTimeout(async () => {
          await fetchStatus()
          setBotLoading(false)
        }, 1000)
      } else {
        setBotLoading(false)
      }
    } catch {
      setBotLoading(false)
    }
  }

  const formatTime = useCallback((date) => {
    return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }, [])

  // Derived stats (Dados reais da API)
  const isTestnetAPI = botStatus ? botStatus.modo.includes("TESTNET") : isTestnet
  const modoAPI = botStatus ? botStatus.modo : "DESCONECTADO"
  
  const posicoes = botStatus?.posicoes || []
  const totalPnl = botStatus?.pnl_dia || 0
  const totalTrades = botStatus?.trades_dia || 0
  const wins = botStatus?.wins_dia || 0
  const winRate = totalTrades > 0 ? ((wins / totalTrades) * 100).toFixed(1) : "0.0"
  
  const saldo = botStatus?.saldo || 0
  const drawdownUsed = saldo > 0 ? ((Math.abs(totalPnl < 0 ? totalPnl : 0) / saldo) * 100).toFixed(2) : "0.00"
  
  const clientError = botStatus?.client_error || null;

  return (
    <div className="app-container">
      {/* ── Header ─────────────────────────────────────────────── */}
      <header className="header animate-in">
        <div className="header-left">
          <div className="logo">🤖</div>
          <div>
            <h1>Trading Bot Dashboard</h1>
            <span className="header-subtitle">
              Binance Automated Trading System &nbsp;•&nbsp; {formatTime(currentTime)}
            </span>
          </div>
        </div>
        <div className="header-right">
          <span className={`badge ${isTestnetAPI ? 'badge-testnet' : 'badge-live'}`}>
            <span className={`pulse-dot ${isTestnetAPI ? 'pulse-dot-amber' : 'pulse-dot-red'}`}></span>
            {modoAPI}
          </span>
          <span className={`badge ${apiConnected ? (botOnline ? 'badge-online' : 'badge-offline') : 'badge-offline'}`}>
            <span className={`pulse-dot ${botOnline ? 'pulse-dot-green' : ''}`}></span>
            {!apiConnected ? 'API Off' : botOnline ? 'Online' : 'Offline'}
          </span>
          <div className="power-wrapper">
            <button
              id="power-toggle-btn"
              className={`power-toggle${botOnline ? ' active' : ''}${botLoading ? ' loading' : ''}`}
              onClick={toggleBot}
              disabled={!apiConnected || botLoading}
              title={botOnline ? 'Desativar Bot' : 'Ativar Bot'}
            >
              <PowerIcon />
            </button>
            <span className={`power-label${botOnline ? ' active' : ''}`}>
              {botLoading ? '...' : botOnline ? 'Ativo' : 'Parado'}
            </span>
          </div>
        </div>
      </header>

      {/* ── Error Banner ─────────────────────────────────────────── */}
      {clientError && (
        <div className="card animate-in" style={{ borderColor: 'var(--rose-500)', backgroundColor: 'rgba(244, 63, 94, 0.05)', marginBottom: '1.5rem' }}>
          <div className="card-body" style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            <div style={{ fontSize: '2rem' }}>🛑</div>
            <div>
              <h3 style={{ color: 'var(--rose-400)', margin: '0 0 0.5rem 0' }}>Erro Crítico de Conexão na Binance</h3>
              <p style={{ color: 'var(--neutral-300)', margin: 0, fontSize: '0.9rem' }}>
                O bot não conseguiu conectar à conta para buscar o saldo. <br/>
                <strong style={{ color: 'var(--rose-300)' }}>Detalhes do Erro:</strong> <code>{clientError}</code>
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── Stats Grid ─────────────────────────────────────────── */}
      <div className="stats-grid">
        <div className="stat-card accent-indigo animate-in animate-in-delay-1">
          <div className="stat-label">Saldo USDT</div>
          <div className="stat-value neutral">${saldo.toFixed(2)}</div>
          <div className="stat-detail">Capital inicial: $1,000.00</div>
        </div>

        <div className="stat-card accent-emerald animate-in animate-in-delay-2">
          <div className="stat-label">PnL do Dia</div>
          <div className={`stat-value ${totalPnl >= 0 ? 'positive' : 'negative'}`}>
            {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}
          </div>
          <div className="stat-detail">
            {totalPnl >= 0 ? '📈' : '📉'} {((totalPnl / 1000) * 100).toFixed(2)}% do capital
          </div>
        </div>

        <div className="stat-card accent-cyan animate-in animate-in-delay-3">
          <div className="stat-label">Win Rate</div>
          <div className="stat-value neutral">{winRate}%</div>
          <div className="stat-detail">{wins}W / {totalTrades - wins}L de {totalTrades} trades</div>
        </div>

        <div className="stat-card accent-amber animate-in animate-in-delay-4">
          <div className="stat-label">Posições Abertas</div>
          <div className="stat-value neutral">{posicoes.length}/5</div>
          <div className="stat-detail">Drawdown usado: {drawdownUsed}%</div>
        </div>

        <div className="stat-card accent-rose animate-in animate-in-delay-5">
          <div className="stat-label">Risco por Trade</div>
          <div className="stat-value neutral">1.0%</div>
          <div className="stat-detail">1% do saldo atual</div>
        </div>
      </div>

      {/* ── Main Grid ──────────────────────────────────────────── */}
      <div className="main-grid">
        {/* Positions */}
        <div className="card animate-in animate-in-delay-2">
          <div className="card-header">
            <span className="card-title">📊 Posições Abertas</span>
            <span className="badge badge-online" style={{ fontSize: '0.7rem', padding: '3px 8px' }}>
              {posicoes.length} ativas
            </span>
          </div>
          <div className="card-body">
            {posicoes.length > 0 ? (
              <ul className="positions-list">
                {posicoes.map((pos, i) => {
                  const pnlNum = pos.pnl || 0;
                  return (
                  <li key={i} className="position-item" style={{ animation: `slideIn 0.3s ease ${i * 0.1}s both` }}>
                    <span className={`position-dir ${pos.direcao.toLowerCase()}`}>
                      {pos.direcao}
                    </span>
                    <div className="position-pair">
                      {pos.par}
                      <span>{pos.confirmacoes} conf.</span>
                    </div>
                    <span className="position-price">
                      Entry: ${parseFloat(pos.entry).toLocaleString()}
                    </span>
                    <span className={`position-pnl ${pnlNum >= 0 ? 'positive' : 'negative'}`}>
                      {pnlNum >= 0 ? '+' : ''}{pnlNum.toFixed(2)}
                    </span>
                    <span className="position-conf">
                      SL: {pos.sl} | TP: {pos.tp}
                    </span>
                  </li>
                )})}
              </ul>
            ) : (
              <div className="empty-state">
                <div className="emoji">🔍</div>
                <p>Nenhuma posição aberta no momento</p>
              </div>
            )}
          </div>
        </div>

        {/* Logs */}
        <div className="card animate-in animate-in-delay-3">
          <div className="card-header">
            <span className="card-title">📋 Log em Tempo Real</span>
            <button className="btn btn-outline" style={{ padding: '4px 12px', fontSize: '0.75rem' }} onClick={() => setLogs([])}>
              Limpar
            </button>
          </div>
          <div className="card-body">
            <div className="log-feed">
              {logs.map((log, i) => (
                <div key={i} className="log-entry" style={{ animation: `slideIn 0.3s ease 0s both` }}>
                  <span className="log-time">{log.time}</span>
                  <span className={`log-level ${log.level}`}>
                    {log.level.toUpperCase()}
                  </span>
                  <span className="log-message">{log.msg}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Market Overview */}
        <div className="card animate-in animate-in-delay-4">
          <div className="card-header">
            <span className="card-title">🔥 Top Movers 24h</span>
          </div>
          <div className="card-body">
            <div className="pairs-grid">
              {DEMO_PAIRS.map((pair, i) => (
                <div key={i} className="pair-chip" style={{ animation: `fadeInUp 0.3s ease ${i * 0.05}s both` }}>
                  <div className="pair-name">{pair.symbol.replace('USDT', '')}</div>
                  <div className={`pair-change ${parseFloat(pair.change) >= 0 ? 'positive' : 'negative'}`}>
                    {parseFloat(pair.change) >= 0 ? '+' : ''}{pair.change}%
                  </div>
                  <div className="pair-vol">Vol: ${pair.vol}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Settings */}
        <div className="card animate-in animate-in-delay-5">
          <div className="card-header">
            <span className="card-title">⚙️ Configuração Ativa</span>
          </div>
          <div className="card-body">
            <div className="settings-grid">
              <div className="setting-item">
                <span className="setting-label">Capital Inicial</span>
                <span className="setting-value">$1,000</span>
              </div>
              <div className="setting-item">
                <span className="setting-label">Risco/Trade</span>
                <span className="setting-value">1%</span>
              </div>
              <div className="setting-item">
                <span className="setting-label">Max Posições</span>
                <span className="setting-value">5</span>
              </div>
              <div className="setting-item">
                <span className="setting-label">Drawdown Max</span>
                <span className="setting-value">3%</span>
              </div>
              <div className="setting-item">
                <span className="setting-label">Alavancagem</span>
                <span className="setting-value">1x</span>
              </div>
              <div className="setting-item">
                <span className="setting-label">R:R Mínimo</span>
                <span className="setting-value">1:1.5</span>
              </div>
              <div className="setting-item">
                <span className="setting-label">Ciclo</span>
                <span className="setting-value">5 min</span>
              </div>
              <div className="setting-item">
                <span className="setting-label">Tendência</span>
                <span className="setting-value">EMA200 4h</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer className="footer">
        Trading Bot v1.0 &nbsp;•&nbsp; Binance Automated Trading &nbsp;•&nbsp;
        Dados {isTestnet ? 'de demonstração (Testnet)' : 'em tempo real'} &nbsp;•&nbsp;
        Nunca invista mais do que pode perder
      </footer>
    </div>
  )
}

export default App
