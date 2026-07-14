import { useState, useEffect } from 'react'
import { ArrowLeft, CheckCircle, Loader2, XCircle, Target, Star, Headphones, User } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-test-env-c5nbfc5meq-uc.a.run.app"

function fmtDateTimeBR(iso) {
  if (!iso) return '-'
  try { return new Date(iso).toLocaleString('pt-BR') } catch { return iso }
}

function sentimentEmoji(s) {
  if (!s) return '⚪'
  const pos = ['positivo','agradecido','calmo','paciente','alegre','empatico','empático','satisfeito','grato','feliz']
  const neg = ['irritado','sarcastico','sarcástico','raiva','triste','frustrado','impaciente','agressivo','hostil','desinteressado','indiferente']
  const low = s.toLowerCase()
  if (pos.some(p => low.includes(p))) return '🟢'
  if (neg.some(n => low.includes(n))) return '🔴'
  return '🟡'
}

function parseAnalysis(call) {
  if (!call) return null
  let raw = call.raw_evaluation
  if (typeof raw === 'string') {
    try { raw = JSON.parse(raw) } catch { return null }
  }
  return raw || null
}

export default function BatchDashboard({ callIds, onBack, onInspectCall }) {
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

  const concluded = calls.filter(c => (c.status || '') === 'Concluído')
  const processing = calls.filter(c => (c.status || '') !== 'Concluído' && !(c.status || '').startsWith('Erro'))
  const errors = calls.filter(c => (c.status || '').startsWith('Erro'))

  const avgQA = concluded.length ? Math.round(concluded.reduce((a, c) => a + (c.nota_qualidade_operador || c.nota || 0), 0) / concluded.length) : 0
  const avgNPS = concluded.length ? (concluded.reduce((a, c) => a + (c.nota_sentimento_cliente || 0), 0) / concluded.length).toFixed(1) : 0

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse space-y-6">
          <div className="h-10 w-64 bg-black/5 rounded-xl" />
          <div className="h-20 bg-black/5 rounded-2xl" />
          <div className="h-20 bg-black/5 rounded-2xl" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={onBack} className="p-2 bg-surface hover:bg-black/10 rounded-xl transition-colors"><ArrowLeft size={20} /></button>
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
        <button onClick={onBack} className="p-2 bg-surface hover:bg-black/10 rounded-xl transition-colors shrink-0"><ArrowLeft size={20} /></button>
        <div>
          <h2 className="text-xl font-bold text-textMain">Painel do Grupo</h2>
          <p className="text-sm text-textMuted mt-1">{calls.length} chamada(s) selecionada(s)</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-panel p-4 text-center">
          <div className="text-sm text-textMuted mb-1">Concluídas</div>
          <div className="text-3xl font-bold text-green-600">{concluded.length}<span className="text-base text-textMuted font-normal">/{calls.length}</span></div>
        </div>
        <div className="glass-panel p-4 text-center">
          <div className="text-sm text-textMuted mb-1">QA Médio</div>
          <div className="text-3xl font-bold text-primary">{avgQA}<span className="text-base text-textMuted font-normal">/100</span></div>
        </div>
        <div className="glass-panel p-4 text-center">
          <div className="text-sm text-textMuted mb-1">NPS Médio</div>
          <div className="text-3xl font-bold text-green-500">{avgNPS}<span className="text-base text-textMuted font-normal">/10</span></div>
        </div>
        <div className="glass-panel p-4 text-center">
          <div className="text-sm text-textMuted mb-1">Processando</div>
          <div className="text-3xl font-bold text-orange-500">{processing.length + errors.length}</div>
        </div>
      </div>

      {/* Legenda */}
      <div className="flex gap-4 text-xs text-textMuted">
        <span className="flex items-center gap-1"><CheckCircle size={12} className="text-green-500" /> Concluído</span>
        <span className="flex items-center gap-1"><Loader2 size={12} className="text-primary animate-spin" /> Processando</span>
        <span className="flex items-center gap-1"><XCircle size={12} className="text-red-500" /> Erro</span>
      </div>

      {/* Cards */}
      <div className="space-y-3">
        {calls.map(call => {
          const cid = call.id || call.call_id || ''
          const analysis = parseAnalysis(call)
          const fases = analysis?.fases || {}
          const statusColor = (call.status || '') === 'Concluído' ? 'border-green-300 bg-green-50/30' :
            (call.status || '').startsWith('Erro') ? 'border-red-300 bg-red-50/30' :
            'border-yellow-300 bg-yellow-50/30'
          const statusDot = (call.status || '') === 'Concluído' ? <CheckCircle size={14} className="text-green-500" /> :
            (call.status || '').startsWith('Erro') ? <XCircle size={14} className="text-red-500" /> :
            <Loader2 size={14} className="text-primary animate-spin" />

          return (
            <div key={cid} className={`rounded-2xl border-l-4 p-5 shadow-sm ${statusColor} bg-surface`}>
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  {/* Header: nome + status */}
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <h3 className="font-bold text-textMain truncate">{call.filename || 'Sem nome'}</h3>
                    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-white border">
                      {statusDot} {call.status}
                    </span>
                  </div>

                  {/* Metadados */}
                  <div className="text-xs text-textMuted mb-2 flex flex-wrap gap-2">
                    <span>{fmtDateTimeBR(call.uploaded_at)}</span>
                    {analysis?.nome_atendente && (
                      <span className="bg-black/5 px-2 py-0.5 rounded-full">Atendente: {analysis.nome_atendente}</span>
                    )}
                    {analysis?.classificacao_motivo && (
                      <span className="bg-primary/10 text-primary px-2 py-0.5 rounded-full">{analysis.classificacao_motivo}</span>
                    )}
                  </div>

                  {/* QA + NPS + Fases */}
                  {call.status === 'Concluído' && (
                    <div className="flex items-center gap-4 flex-wrap">
                      <div className="flex items-center gap-1.5">
                        <Target size={14} className="text-primary" />
                        <span className="text-sm font-bold text-textMain">{call.nota_qualidade_operador || call.nota || '-'}</span>
                        <span className="text-xs text-textMuted">/100</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Star size={14} className="text-green-500" />
                        <span className="text-sm font-bold text-green-600">{call.nota_sentimento_cliente || 0}</span>
                        <span className="text-xs text-textMuted">/10</span>
                      </div>
                      {/* Sentimentos por fase */}
                      <div className="flex items-center gap-1 text-xs">
                        {['apresentacao','resolucao','fechamento'].map(f => (
                          <span key={f} title={`Fase ${f}: ${fases[f]?.sentimento_cliente || '-'}`}>
                            {sentimentEmoji(fases[f]?.sentimento_cliente)}
                          </span>
                        ))}
                        <span className="text-textMuted ml-1">fases</span>
                      </div>
                    </div>
                  )}

                  {/* Sentimentos em texto */}
                  {call.status === 'Concluído' && (analysis?.sentimentos_cliente?.length > 0 || analysis?.sentimentos_operador?.length > 0) && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {analysis.sentimentos_cliente?.slice(0, 3).map((s, i) => {
                        const txt = typeof s === 'string' ? s : s?.sentimento || s?.label || ''
                        return <span key={`c-${i}`} className="text-[10px] bg-black/5 px-1.5 py-0.5 rounded-full">{txt}</span>
                      })}
                      {analysis.sentimentos_operador?.slice(0, 3).map((s, i) => {
                        const txt = typeof s === 'string' ? s : s?.sentimento || s?.label || ''
                        return <span key={`o-${i}`} className="text-[10px] bg-primary/5 text-primary px-1.5 py-0.5 rounded-full">{txt}</span>
                      })}
                    </div>
                  )}
                </div>

                {/* Botão Inspecionar */}
                <button
                  onClick={() => onInspectCall && onInspectCall(cid)}
                  disabled={(call.status || '') !== 'Concluído' && !(call.status || '').startsWith('Erro')}
                  className="shrink-0 text-primary hover:text-primary/80 font-medium text-sm disabled:opacity-30 transition-colors"
                >
                  {(call.status || '') === 'Concluído' ? 'Inspecionar →' : (call.status || '').startsWith('Erro') ? 'Detalhes →' : '⏳'}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
