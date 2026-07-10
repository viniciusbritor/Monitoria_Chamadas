import { useState, useEffect } from 'react'
import { ArrowLeft, CheckCircle, Loader2, XCircle, Target, Star, Headphones, User, FileText } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-test-env-c5nbfc5meq-uc.a.run.app"

function fmtDateTimeBR(iso) {
  if (!iso) return '-'
  try { return new Date(iso).toLocaleString('pt-BR') } catch { return iso }
}

export default function BatchDashboard({ callIds, onBack }) {
  const [calls, setCalls] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!callIds || callIds.length === 0) {
      setError("Nenhuma chamada selecionada.")
      setLoading(false)
      return
    }
    const fetchBatch = async () => {
      try {
        const token = localStorage.getItem('auth_token')
        const idsParam = callIds.join(',')
        const res = await axios.get(`${API_URL}/api/calls?ids=${encodeURIComponent(idsParam)}`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        setCalls(res.data)
      } catch (err) {
        setError(`Erro ao carregar: ${err.response?.data?.detail || err.message}`)
      } finally {
        setLoading(false)
      }
    }
    fetchBatch()
  }, [callIds])

  const concluded = calls.filter(c => c.status === 'Concluído')
  const inQueue = calls.filter(c => c.status === 'Na Fila de Processamento...')
  const processing = calls.filter(c => c.status !== 'Concluído' && !c.status.startsWith('Erro') && c.status !== 'Na Fila de Processamento...')
  const errors = calls.filter(c => c.status.startsWith('Erro'))

  const avgQA = concluded.length
    ? Math.round(concluded.reduce((a, c) => a + (c.nota_qualidade_operador || c.nota || 0), 0) / concluded.length)
    : 0
  const avgNPS = concluded.length
    ? (concluded.reduce((a, c) => a + (c.nota_sentimento_cliente || 0), 0) / concluded.length).toFixed(1)
    : 0

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse space-y-6">
          <div className="h-10 w-64 bg-black/5 rounded-xl" />
          <div className="h-32 bg-black/5 rounded-2xl" />
          <div className="h-24 bg-black/5 rounded-2xl" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={onBack} className="p-2 bg-surface hover:bg-black/10 rounded-xl transition-colors">
            <ArrowLeft size={20} />
          </button>
          <h2 className="text-xl font-bold text-textMain">Erro ao carregar grupo</h2>
        </div>
        <div className="glass-panel p-8 text-center">
          <p className="text-red-600">{error}</p>
          <button onClick={onBack} className="mt-4 bg-primary text-white py-2 px-6 rounded-xl">Voltar</button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={onBack} className="p-2 bg-surface hover:bg-black/10 rounded-xl transition-colors shrink-0">
          <ArrowLeft size={20} />
        </button>
        <div>
          <h2 className="text-xl font-bold text-textMain">Grupo de Chamadas</h2>
          <p className="text-sm text-textMuted mt-1">{calls.length} chamada(s) selecionada(s)</p>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-panel p-4 text-center">
          <div className="text-sm text-textMuted mb-1">Concluídas</div>
          <div className="text-3xl font-bold text-green-600">{concluded.length}
            <span className="text-base text-textMuted font-normal">/{calls.length}</span>
          </div>
        </div>
        <div className="glass-panel p-4 text-center">
          <div className="text-sm text-textMuted mb-1">QA Médio</div>
          <div className="text-3xl font-bold text-primary">{avgQA}
            <span className="text-base text-textMuted font-normal">/100</span>
          </div>
        </div>
        <div className="glass-panel p-4 text-center">
          <div className="text-sm text-textMuted mb-1">NPS Médio</div>
          <div className="text-3xl font-bold text-green-500">{avgNPS}
            <span className="text-base text-textMuted font-normal">/10</span>
          </div>
        </div>
        <div className="glass-panel p-4 text-center">
          <div className="text-sm text-textMuted mb-1">Processando</div>
          <div className="text-3xl font-bold text-orange-500">{processing.length + inQueue.length}</div>
        </div>
      </div>

      {/* Legenda */}
      {calls.length > 0 && (
        <div className="flex gap-4 text-xs text-textMuted">
          <span className="flex items-center gap-1"><CheckCircle size={12} className="text-green-500" /> Concluído</span>
          <span className="flex items-center gap-1"><Loader2 size={12} className="text-primary animate-spin" /> Processando</span>
          <span className="flex items-center gap-1"><XCircle size={12} className="text-red-500" /> Erro</span>
        </div>
      )}

      {/* Lista */}
      <div className="glass-panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-background text-textMuted text-sm">
                <th className="p-4 font-medium">Arquivo</th>
                <th className="p-4 font-medium">Data</th>
                <th className="p-4 font-medium">Status</th>
                <th className="p-4 font-medium">QA</th>
                <th className="p-4 font-medium text-right">Ação</th>
              </tr>
            </thead>
            <tbody>
              {calls.map(call => {
                const cid = call.id || call.call_id || ''
                return (
                  <tr key={cid} className="border-b border-black/5 hover:bg-black/5 transition-colors">
                    <td className="p-4">
                      <span className="font-medium text-textMain">{call.filename || 'Sem nome'}</span>
                    </td>
                    <td className="p-4 text-sm text-textMuted">{fmtDateTimeBR(call.uploaded_at)}</td>
                    <td className="p-4">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                        call.status === 'Concluído' ? 'bg-green-50 text-green-700 border-green-200' :
                        call.status.startsWith('Erro') ? 'bg-red-50 text-red-700 border-red-200' :
                        'bg-yellow-50 text-yellow-700 border-yellow-200'
                      }`}>
                        {call.status === 'Concluído' ? <CheckCircle size={12} /> :
                         call.status.startsWith('Erro') ? <XCircle size={12} /> :
                         <Loader2 size={12} className="animate-spin" />}
                        {call.status}
                      </span>
                    </td>
                    <td className="p-4 font-bold">{call.status === 'Concluído' ? (call.nota_qualidade_operador || call.nota || '-') : '-'}</td>
                    <td className="p-4 text-right">
                      <button onClick={() => onBack && onBack()}
                        className="text-primary text-sm font-medium hover:text-primary/80">
                        Inspecionar
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
