import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { AlertTriangle, RefreshCw, Trash2, RotateCw, Eye, Server, Activity, Inbox } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-test-env-c5nbfc5meq-uc.a.run.app"

function QueueManager({ userToken, onBack }) {
  const [stats, setStats] = useState(null)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedMsg, setSelectedMsg] = useState(null)
  const [purgeConfirm, setPurgeConfirm] = useState('')
  const [purging, setPurging] = useState(false)
  const [refreshTick, setRefreshTick] = useState(0)
  const intervalRef = useRef(null)

  const authHeaders = { headers: { Authorization: `Bearer ${userToken}` } }

  const fetchAll = async () => {
    setLoading(true)
    setError(null)
    try {
      const [statsRes, msgsRes] = await Promise.all([
        axios.get(`${API_URL}/api/queue/stats`, authHeaders),
        axios.get(`${API_URL}/api/queue/messages?limit=50`, authHeaders),
      ])
      setStats(statsRes.data)
      setMessages(msgsRes.data.messages || [])
    } catch (e) {
      const code = e.response?.status
      if (code === 403) {
        setError('Acesso restrito a administradores')
      } else {
        setError(`Erro: ${e.response?.data?.detail || e.message}`)
      }
    } finally {
      setLoading(false)
    }
  }

  // Short-polling 5s (consistente com Dashboard.jsx)
  useEffect(() => {
    fetchAll()
    intervalRef.current = setInterval(fetchAll, 5000)
    return () => clearInterval(intervalRef.current)
  }, [])

  const handleAck = async (msg) => {
    if (!confirm(`Descartar mensagem ${msg.message_id.slice(0, 12)}... ?`)) return
    try {
      await axios.post(
        `${API_URL}/api/queue/messages/${encodeURIComponent(msg.message_id)}/ack?ack_id=${encodeURIComponent(msg.ack_id)}`,
        {},
        authHeaders,
      )
      setRefreshTick(t => t + 1)
      fetchAll()
    } catch (e) {
      alert(`Falha: ${e.response?.data?.detail || e.message}`)
    }
  }

  const handleRetry = async (msg) => {
    if (!confirm(`Reprocessar mensagem ${msg.message_id.slice(0, 12)}... ?`)) return
    try {
      // list_pending devolve payload completo + attributes para reuso
      const payload = msg.payload || ''
      const attributes = msg.attributes || {}
      await axios.post(
        `${API_URL}/api/queue/messages/${encodeURIComponent(msg.message_id)}/retry`,
        { payload, attributes },
        authHeaders,
      )
      setRefreshTick(t => t + 1)
      fetchAll()
    } catch (e) {
      alert(`Falha: ${e.response?.data?.detail || e.message}`)
    }
  }

  const handlePurge = async () => {
    if (purgeConfirm !== 'CONFIRMAR') return
    setPurging(true)
    try {
      await axios.post(
        `${API_URL}/api/queue/purge?confirm=true`,
        {},
        authHeaders,
      )
      setPurgeConfirm('')
      setRefreshTick(t => t + 1)
      fetchAll()
    } catch (e) {
      alert(`Falha: ${e.response?.data?.detail || e.message}`)
    } finally {
      setPurging(false)
    }
  }

  const formatAge = (seconds) => {
    if (!seconds && seconds !== 0) return '-'
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
    return `${Math.floor(seconds / 3600)}h`
  }

  const formatTime = (iso) => {
    if (!iso) return '-'
    try {
      const d = new Date(iso)
      return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch { return '-' }
  }

  const workerHealthy = stats?.worker_healthy
  const messageCount = stats?.message_count ?? 0
  const oldest = stats?.oldest_unacked_seconds

  return (
    <div className="space-y-6">
      {/* Header com botao Voltar */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-textMain flex items-center gap-2">
            <Inbox size={24} className="text-primary" />
            Queue Manager
          </h1>
          <p className="text-sm text-textMuted mt-1">
            Mensagens pendentes no Pub/Sub <code className="text-xs bg-black/5 px-1 rounded">{stats?.subscription || '...'}</code>
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchAll}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-black/10 hover:bg-black/5 text-sm font-semibold disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Atualizar
          </button>
          {onBack && (
            <button
              onClick={onBack}
              className="px-4 py-2 rounded-xl border border-black/10 hover:bg-black/5 text-sm font-semibold"
            >
              Voltar
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="glass-panel p-4 border-l-4 border-red-500">
          <div className="flex items-center gap-2 text-red-600">
            <AlertTriangle size={20} />
            <span className="font-semibold">{error}</span>
          </div>
        </div>
      )}

      {/* Cards de saude */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="glass-panel p-4">
          <div className="flex items-center gap-2 text-sm text-textMuted">
            <Server size={16} />
            <span>Worker</span>
          </div>
          <div className={`mt-2 text-lg font-bold ${workerHealthy === true ? 'text-green-600' : workerHealthy === false ? 'text-red-600' : 'text-textMuted'}`}>
            {workerHealthy === true ? '● Saudavel' : workerHealthy === false ? '● Indisponivel' : '● ...'}
          </div>
        </div>
        <div className="glass-panel p-4">
          <div className="flex items-center gap-2 text-sm text-textMuted">
            <Inbox size={16} />
            <span>Mensagens pendentes</span>
          </div>
          <div className={`mt-2 text-3xl font-bold ${messageCount > 0 ? 'text-orange-600' : 'text-green-600'}`}>
            {messageCount}
          </div>
        </div>
        <div className="glass-panel p-4">
          <div className="flex items-center gap-2 text-sm text-textMuted">
            <Activity size={16} />
            <span>Mais antiga</span>
          </div>
          <div className="mt-2 text-3xl font-bold text-textMain">
            {oldest !== null && oldest !== undefined ? formatAge(oldest) : '-'}
          </div>
        </div>
        <div className="glass-panel p-4">
          <div className="flex items-center gap-2 text-sm text-textMuted">
            <RotateCw size={16} />
            <span>Ack deadline</span>
          </div>
          <div className="mt-2 text-3xl font-bold text-textMain">
            {stats?.ack_deadline_seconds ? `${stats.ack_deadline_seconds}s` : '-'}
          </div>
        </div>
      </div>

      {/* Tabela de mensagens */}
      <div className="glass-panel overflow-hidden">
        <div className="p-4 border-b border-black/5 flex items-center justify-between">
          <h2 className="font-semibold text-textMain">Mensagens</h2>
          <span className="text-xs text-textMuted">
            {messages.length} visivel{messages.length !== 1 ? 'is' : ''} | tick: {refreshTick}
          </span>
        </div>
        {messages.length === 0 ? (
          <div className="p-12 text-center text-textMuted">
            <Inbox size={48} className="mx-auto mb-3 opacity-30" />
            <p>Nenhuma mensagem pendente. Fila limpa.</p>
          </div>
        ) : (
          <div className="overflow-x-auto overflow-y-auto max-h-96 border border-black/5 rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-black/5 text-xs text-textMuted uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3 text-left">Message ID</th>
                  <th className="px-4 py-3 text-left">Filename</th>
                  <th className="px-4 py-3 text-left">Publicada</th>
                  <th className="px-4 py-3 text-left">Acoes</th>
                </tr>
              </thead>
              <tbody>
                {messages.map((msg) => {
                  const filename = msg.attributes?.filename || '-'
                  return (
                    <tr key={msg.message_id} className="border-t border-black/5 hover:bg-black/[0.02]">
                      <td className="px-4 py-3 font-mono text-xs">
                        {msg.message_id.slice(0, 16)}...
                      </td>
                      <td className="px-4 py-3 max-w-xs truncate" title={filename}>
                        {filename}
                      </td>
                      <td className="px-4 py-3 text-textMuted">{formatTime(msg.publish_time)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setSelectedMsg(msg)}
                            className="p-1.5 rounded hover:bg-black/5 text-textMuted"
                            title="Inspecionar"
                          >
                            <Eye size={16} />
                          </button>
                          <button
                            onClick={() => handleRetry(msg)}
                            className="p-1.5 rounded hover:bg-green-50 text-green-600"
                            title="Reprocessar"
                          >
                            <RotateCw size={16} />
                          </button>
                          <button
                            onClick={() => handleAck(msg)}
                            className="p-1.5 rounded hover:bg-red-50 text-red-600"
                            title="Descartar"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Purge section */}
      <div className="glass-panel p-4 border-l-4 border-red-500">
        <h3 className="font-semibold text-textMain flex items-center gap-2">
          <Trash2 size={18} className="text-red-600" />
          Limpar todas as mensagens pendentes
        </h3>
        <p className="text-sm text-textMuted mt-1">
          Acao irreversivel. As mensagens serao descartadas e nao serao processadas pelo worker.
        </p>
        <div className="mt-3 flex gap-2 items-center">
          <input
            type="text"
            value={purgeConfirm}
            onChange={e => setPurgeConfirm(e.target.value)}
            placeholder='Digite "CONFIRMAR" para habilitar'
            className="flex-1 px-3 py-2 rounded-xl border border-black/10 text-sm focus:border-red-500 focus:outline-none"
          />
          <button
            onClick={handlePurge}
            disabled={purgeConfirm !== 'CONFIRMAR' || purging}
            className="px-4 py-2 rounded-xl bg-red-600 text-white font-semibold text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-red-700 transition-colors"
          >
            {purging ? 'Limpando...' : 'Limpar tudo'}
          </button>
        </div>
      </div>

      {/* Modal de inspecao */}
      {selectedMsg && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
          onClick={() => setSelectedMsg(null)}
        >
          <div
            className="glass-panel max-w-2xl w-full max-h-[80vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="p-4 border-b border-black/10 flex items-center justify-between">
              <h3 className="font-bold text-textMain">Mensagem</h3>
              <button
                onClick={() => setSelectedMsg(null)}
                className="text-textMuted hover:text-textMain"
              >
                ✕
              </button>
            </div>
            <div className="p-4 space-y-3 text-sm">
              <div>
                <div className="text-xs text-textMuted">Message ID</div>
                <div className="font-mono text-xs break-all bg-black/5 p-2 rounded mt-1">
                  {selectedMsg.message_id}
                </div>
              </div>
              <div>
                <div className="text-xs text-textMuted">Publish Time</div>
                <div className="mt-1">{selectedMsg.publish_time || '-'}</div>
              </div>
              <div>
                <div className="text-xs text-textMuted">Attributes</div>
                <pre className="mt-1 font-mono text-xs bg-black/5 p-2 rounded overflow-x-auto">
                  {JSON.stringify(selectedMsg.attributes, null, 2)}
                </pre>
              </div>
              <div>
                <div className="text-xs text-textMuted">Payload (JSON)</div>
                <pre className="mt-1 font-mono text-xs bg-black/5 p-2 rounded overflow-x-auto max-h-64 overflow-y-auto">
                  {(() => {
                    try {
                      return JSON.stringify(JSON.parse(selectedMsg.payload || '{}'), null, 2)
                    } catch {
                      return selectedMsg.payload || '(vazio)'
                    }
                  })()}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default QueueManager
