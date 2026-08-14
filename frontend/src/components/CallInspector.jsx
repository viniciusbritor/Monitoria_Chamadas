import { useState, useEffect } from 'react'
import {
  ArrowLeft, CheckCircle2, AlertTriangle, ThumbsUp,
  ShieldAlert, ChevronDown, ChevronUp, Headphones, User,
  FileText, Star, MessageSquare, Target, Volume2, FileSpreadsheet, Presentation
} from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-test-env-894828119087.us-central1.run.app"

function ScoreBadge({ value, max, color = 'primary' }) {
  const pct = max ? (value / max) * 100 : 0
  const colors = {
    primary: 'bg-primary/10 text-primary border-primary/20',
    green: 'bg-green-50 text-green-700 border-green-200',
    yellow: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    red: 'bg-red-50 text-red-700 border-red-200',
  }
  const c = pct >= 80 ? colors.green : pct >= 50 ? colors.yellow : colors.red
  return (
    <span className={`px-2.5 py-1 rounded-full font-bold text-xs border ${c}`}>
      {value}/{max}
    </span>
  )
}

function SentimentBadge({ value }) {
  if (!value) return null
  // Dinamico: match keywords positivo/negativo para determinar cor
  const lower = value.toLowerCase()
  const positivo = ['positivo', 'agradecido', 'calmo', 'paciente', 'alegre', 'empatico', 'empatia',
    'satisfeito', 'grato', 'feliz', 'otimista', 'confiante', 'esperancoso', 'esperançoso', 'educado']
  const negativo = ['irritado', 'sarcastico', 'sarcástico', 'raiva', 'triste', 'frustrado',
    'impaciente', 'agressivo', 'hostil', 'desinteressado', 'indiferente', 'preocupado', 'ansioso',
    'insatisfeito', 'grosseria', 'grosso', 'reclamacao', 'reclamação']
  
  if (positivo.some(p => lower.includes(p))) {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
      🟢 {value}
    </span>
  }
  if (negativo.some(n => lower.includes(n))) {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
      🔴 {value}
    </span>
  }
  return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700">
    🟡 {value}
  </span>
}

function SentimentList({ sentiments, emptyText = "Nenhum sentimento" }) {
  if (!Array.isArray(sentiments) || sentiments.length === 0) {
    return <span className="text-xs text-textMuted italic">{emptyText}</span>
  }
  return (
    <div className="flex flex-wrap gap-2">
      {sentiments.map((s, i) => {
        const label = typeof s === 'string' ? s : s?.sentimento || s?.label || ''
        const prob = typeof s === 'object' ? s?.probabilidade : null
        const pct = prob ? Math.round(prob * 100) : null
        return (
          <span key={i} className="inline-flex items-center gap-1.5 bg-surface text-textMain px-3 py-1 rounded-full text-sm font-medium border border-black/10">
            {label}
            {pct !== null && (
              <span className="text-[10px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded-md">
                {pct}%
              </span>
            )}
          </span>
        )
      })}
    </div>
  )
}

function PhaseCard({ title, icon: Icon, fase }) {
  const qa = fase?.nota_qa || 0
  const nps = fase?.nota_nps || 0
  const sentCliArr = fase?.sentimentos_cliente || (fase?.sentimento_cliente ? [{ sentimento: fase.sentimento_cliente }] : null)
  const sentOpeArr = fase?.sentimentos_operador || (fase?.sentimento_operador ? [{ sentimento: fase.sentimento_operador }] : null)
  return (
    <div className="p-5 rounded-2xl bg-surface border border-black/5 space-y-3 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {Icon && <Icon size={20} className="text-primary shrink-0" />}
          <h4 className="font-bold text-textMain text-base">{title}</h4>
        </div>
        <div className="flex gap-2 text-xs shrink-0 items-center">
          <span className="px-1.5 py-0.5 rounded font-semibold text-[10px] uppercase tracking-wider bg-gray-100 text-gray-600">QA</span>
          <ScoreBadge value={qa} max={100} />
          <span className="px-1.5 py-0.5 rounded font-semibold text-[10px] uppercase tracking-wider bg-gray-100 text-gray-600">NPS</span>
          <ScoreBadge value={nps} max={10} />
        </div>
      </div>
      <p className="text-sm text-textMuted leading-relaxed">
        {fase?.analise || "Análise não disponível para esta fase."}
      </p>
      {(sentCliArr || sentOpeArr) && (
        <div className="space-y-2 pt-3 border-t border-black/10">
          {sentCliArr && (
            <div>
              <div className="flex items-center gap-1.5 mb-1.5">
                <User size={12} className="text-textMuted" />
                <span className="text-[10px] text-textMuted uppercase tracking-wide font-semibold">Cliente:</span>
              </div>
              <SentimentList sentiments={sentCliArr} />
            </div>
          )}
          {sentOpeArr && (
            <div>
              <div className="flex items-center gap-1.5 mb-1.5">
                <Headphones size={12} className="text-primary" />
                <span className="text-[10px] text-textMuted uppercase tracking-wide font-semibold">Atendente:</span>
              </div>
              <SentimentList sentiments={sentOpeArr} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function CallInspector({ callId, onBack, autoScroll }) {
  const [call, setCall] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [exporting, setExporting] = useState(false)

  const handleExportExcel = async () => {
    try {
      setExporting(true)
      const token = localStorage.getItem('auth_token')
      const res = await axios.get(`${API_URL}/api/export/excel?ids=${encodeURIComponent(callId)}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `relatorio_${callId.slice(0,8)}.xlsx`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err) {
      alert(`Erro ao exportar Excel: ${err.message}`)
    } finally {
      setExporting(false)
    }
  }

  const handleExportPPTX = async () => {
    try {
      setExporting(true)
      const token = localStorage.getItem('auth_token')
      const res = await axios.get(`${API_URL}/api/export/pptx?ids=${encodeURIComponent(callId)}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `apresentacao_${callId.slice(0,8)}.pptx`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err) {
      alert(`Erro ao exportar PowerPoint: ${err.message}`)
    } finally {
      setExporting(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    console.log('[CallInspector] mount', { callId, isString: typeof callId, length: callId?.length, valid: typeof callId === 'string' && callId.length >= 8 })
    if (!callId || typeof callId !== 'string' || callId.length < 8) {
      console.error('[CallInspector] ID INVALIDO', { callId })
      setError('ID da chamada invalido. Volte ao Dashboard.')
      setLoading(false)
      return
    }
    const fetchCall = async () => {
      try {
        console.log('[CallInspector] fetching', { url: `${API_URL}/api/calls/${callId}` })
        const token = localStorage.getItem('auth_token')
        const res = await axios.get(`${API_URL}/api/calls/${callId}`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        console.log('[CallInspector] response OK', { status: res.status, hasRawEval: !!res.data.raw_evaluation, hasFilename: !!res.data.filename })

        let analysisData = res.data.raw_evaluation
        if (typeof analysisData === 'string') {
          try { analysisData = JSON.parse(analysisData) }
          catch (e) { analysisData = null }
        }

        if (!cancelled) {
          setCall({ ...res.data, analysis: analysisData || {} })
          setError(null)
        }

        try {
          const audioRes = await axios.get(`${API_URL}/api/calls/${callId}/audio`, {
            headers: { Authorization: `Bearer ${token}` }
          })
          if (!cancelled) setAudioUrl(audioRes.data.audio_url)
        } catch (e) {
          const status = e.response?.status
          if (status === 404) setAudioError('Audio expirado ou deletado (retencao de 30 dias).')
          else if (status === 403) setAudioError('Sem permissao para ouvir este audio.')
          else setAudioError('Audio nao disponivel no momento.')
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[CallInspector] fetch ERROR', { status: err.response?.status, message: err.message, data: err.response?.data })
          if (err.response?.status === 403) setError('Sem permissao para visualizar esta chamada.')
          else if (err.response?.status === 404) setError('Chamada nao encontrada.')
          else if (err.response?.status === 401) setError('Sessao expirada. Recomece pelo Portal.')
          else setError(`Erro ao carregar: ${err.message}`)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchCall()
    return () => { cancelled = true }
  }, [callId])

  // Auto-scroll para o player de áudio quando audioUrl carregar
  useEffect(() => {
    if (autoScroll === 'audio-player' && audioUrl) {
      const el = document.getElementById('audio-player')
      if (el) {
        setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'center' }), 300)
      }
    }
  }, [autoScroll, audioUrl])

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse space-y-6">
          <div className="h-10 w-64 bg-black/5 rounded-xl" />
          <div className="h-32 bg-black/5 rounded-2xl" />
          <div className="h-24 bg-black/5 rounded-2xl" />
          <div className="h-24 bg-black/5 rounded-2xl" />
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
          <h2 className="text-xl font-bold text-textMain">Erro ao carregar</h2>
        </div>
        <div className="glass-panel p-8 text-center space-y-4">
          <AlertTriangle size={32} className="text-red-500 mx-auto" />
          <p className="text-red-600 font-medium">{error}</p>
          <button onClick={onBack} className="bg-primary hover:bg-primary/90 text-white font-medium py-2 px-6 rounded-xl">
            Voltar ao Dashboard
          </button>
        </div>
      </div>
    )
  }

  const filename = call?.filename || 'Chamada sem nome'
  const uploadedAt = call?.uploaded_at ? new Date(call.uploaded_at) : new Date()
  const analysis = call?.analysis || {}
  const qaScore = call?.nota_qualidade_operador || call?.nota || 0
  const clientScore = call?.nota_sentimento_cliente || 0
  const iaUtilizada = call?.ia_utilizada || 'IA'
  const fases = analysis?.fases || {}
  const faseInicio = fases?.apresentacao || {}
  const faseMeio = fases?.resolucao || {}
  const faseFim = fases?.fechamento || {}
  const isErro = (call?.status || '').startsWith('Erro')

  return (
    <div className="space-y-6 w-full">

      {/* Cabeçalho */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4 min-w-0 flex-1">
          <button onClick={onBack} className="p-2 bg-surface hover:bg-black/10 rounded-xl transition-colors shrink-0">
            <ArrowLeft size={20} />
          </button>
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-bold text-textMain truncate flex items-center gap-3">
              {filename}
              {audioUrl && (
                <button onClick={() => document.getElementById('audio-player')?.scrollIntoView({ behavior: 'smooth' })}
                  className="text-primary hover:text-primary/80 p-1.5 rounded hover:bg-black/5 transition-colors shrink-0"
                  title="Ouvir chamada">
                  <Volume2 size={18} />
                </button>
              )}
            </h2>
            <div className="text-sm text-textMuted mt-1 flex items-center gap-3 flex-wrap">
              <span>{uploadedAt.toLocaleString('pt-BR')}</span>
              {analysis?.nome_atendente && (
                <span className="text-xs bg-black/5 px-2 py-0.5 rounded-full">
                  Atendente: <b>{analysis.nome_atendente}</b>
                </span>
              )}
              {analysis?.classificacao_motivo && (
                <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full font-medium">
                  {analysis.classificacao_motivo}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            disabled={exporting}
            onClick={handleExportExcel}
            className="flex items-center gap-2 bg-emerald-700 hover:bg-emerald-800 text-white font-medium py-2 px-3.5 rounded-xl text-sm transition-all shadow-sm disabled:opacity-50"
            title="Exportar esta chamada para planilha Excel (.xlsx)"
          >
            <FileSpreadsheet size={16} />
            Exportar Excel
          </button>

          <button
            disabled={exporting}
            onClick={handleExportPPTX}
            className="flex items-center gap-2 bg-amber-700 hover:bg-amber-800 text-white font-medium py-2 px-3.5 rounded-xl text-sm transition-all shadow-sm disabled:opacity-50"
            title="Exportar esta chamada para apresentação PowerPoint (.pptx)"
          >
            <Presentation size={16} />
            Exportar PPTX
          </button>
        </div>
      </div>

      {isErro && (
        <div className="glass-panel border-red-500/30 bg-red-50/80 p-6">
          <div className="flex items-center gap-3">
            <AlertTriangle size={24} className="text-red-500 shrink-0" />
            <div>
              <h3 className="font-bold text-red-700">Processamento nao concluido</h3>
              <p className="text-sm text-red-600 mt-1">{call?.status}</p>
            </div>
          </div>
        </div>
      )}

      {/* Score Cards (compactos, sem IA Utilizada) */}
      <div className="grid grid-cols-2 gap-4">
        <div className="glass-panel p-5 text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <Target size={18} className="text-primary" />
            <h3 className="font-medium text-textMuted text-xs uppercase tracking-wide">QA Score</h3>
          </div>
          <div className="text-4xl font-black text-primary">{qaScore}
            <span className="text-lg text-textMuted font-normal">/100</span>
          </div>
        </div>
        <div className="glass-panel p-5 text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <Star size={18} className="text-green-500" />
            <h3 className="font-medium text-textMuted text-xs uppercase tracking-wide">Sentimento Cliente</h3>
          </div>
          <div className="text-4xl font-black text-green-500">{clientScore}
            <span className="text-lg text-textMuted font-normal">/10</span>
          </div>
        </div>
      </div>

      {/* Layout 2 colunas: esquerda (Humor + Checklist + Erro) | direita (3 Fases + Recom. + Oport.) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Coluna esquerda — 1fr (Humor Cliente, Humor Atendente, Checklist, Erro Crítico) */}
        <div className="lg:col-span-1 space-y-6">
          {/* Humor do Cliente */}
          <div className={`glass-panel p-5 border-l-4 ${
            !analysis?.humor_cliente ? '' :
            ['Positivo','Agradecido','Calmo','Paciente'].includes(analysis.humor_cliente) ? 'border-green-400 bg-green-50/50' :
            analysis.humor_cliente === 'Neutro' ? 'border-yellow-400 bg-yellow-50/50' :
            'border-red-400 bg-red-50/50'
          }`}>
            <div className="flex items-center gap-2 mb-3">
              <User size={18} className="text-textMuted" />
              <h3 className="font-semibold text-textMain">Humor do Cliente</h3>
            </div>
            <SentimentList
              sentiments={analysis?.sentimentos_cliente || []}
              emptyText="Nenhum sentimento detectado"
            />
          </div>

          {/* Humor do Atendente */}
          <div className={`glass-panel p-5 border-l-4 ${
            !analysis?.humor_expert ? '' :
            ['Positivo','Empatico','Empático','Paciente','Alegre','Calmo'].includes(analysis.humor_expert) ? 'border-green-400 bg-green-50/50' :
            analysis.humor_expert === 'Neutro' ? 'border-yellow-400 bg-yellow-50/50' :
            analysis.humor_expert === 'Desinteressado' ? 'border-orange-400 bg-orange-50/50' :
            'border-red-400 bg-red-50/50'
          }`}>
            <div className="flex items-center gap-2 mb-3">
              <Headphones size={18} className="text-primary" />
              <h3 className="font-semibold text-textMain">Humor do Atendente</h3>
            </div>
            <SentimentList
              sentiments={analysis?.sentimentos_operador || []}
              emptyText="Nenhum sentimento detectado"
            />
          </div>

          {/* Checklist de Conformidade (POP) */}
          {Array.isArray(analysis?.checklist_conformidade) && analysis.checklist_conformidade.length > 0 && (
            <div className="glass-panel p-5">
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle2 size={18} className="text-primary" />
                <h3 className="font-semibold text-textMain">Checklist de Conformidade</h3>
              </div>
              <div className="space-y-2">
                {analysis.checklist_conformidade.map((item, i) => (
                  <div key={i} className="flex items-start gap-3 py-2 border-b border-black/5 last:border-0">
                    {item.cumprido ? (
                      <CheckCircle2 size={16} className="text-green-500 shrink-0 mt-0.5" />
                    ) : (
                      <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
                    )}
                    <span className={`text-sm ${item.cumprido ? 'text-textMain' : 'text-red-600 font-medium'}`}>
                      {item.item}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Erro Crítico */}
          <div className={`glass-panel p-5 ${analysis?.erro_critico ? 'border-red-500/30 bg-red-50/80' : ''}`}>
            <div className="flex items-center gap-3">
              <ShieldAlert size={20} className={analysis?.erro_critico ? 'text-red-500' : 'text-green-500'} />
              <div>
                <h3 className="font-semibold text-textMain">Erro Crítico</h3>
                <p className={`text-sm font-medium mt-1 ${analysis?.erro_critico ? 'text-red-600' : 'text-green-600'}`}>
                  {analysis?.erro_critico ? 'SIM — Foram identificados erros fatais' : 'NÃO — Nenhum erro fatal identificado'}
                </p>
              </div>
            </div>
            {Array.isArray(analysis?.erros_fatais_identificados) && analysis.erros_fatais_identificados.length > 0 && (
              <ul className="mt-4 space-y-1 border-t border-red-200 pt-3">
                {analysis.erros_fatais_identificados.map((e, i) => (
                  <li key={i} className="text-sm text-red-600 flex items-start gap-2">
                    <span className="mt-1 shrink-0">•</span> {e}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Pontos Positivos — coluna esquerda */}
          {Array.isArray(analysis?.pontos_positivos) && analysis.pontos_positivos.length > 0 && (
            <div className="glass-panel p-5">
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle2 size={18} className="text-green-500" />
                <h3 className="font-semibold text-textMain">Pontos Positivos</h3>
              </div>
              <ul className="space-y-2">
                {analysis.pontos_positivos.map((p, i) => (
                  <li key={i} className="text-sm text-textMain flex items-start gap-2">
                    <span className="text-green-500 mt-1 shrink-0">•</span> {p}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Pontos de Melhoria — coluna esquerda */}
          {Array.isArray(analysis?.pontos_melhoria) && analysis.pontos_melhoria.length > 0 && (
            <div className="glass-panel p-5">
              <div className="flex items-center gap-2 mb-4">
                <AlertTriangle size={18} className="text-yellow-500" />
                <h3 className="font-semibold text-textMain">Pontos de Melhoria</h3>
              </div>
              <ul className="space-y-2">
                {analysis.pontos_melhoria.map((p, i) => (
                  <li key={i} className="text-sm text-textMain flex items-start gap-2">
                    <span className="text-yellow-500 mt-1 shrink-0">•</span> {p}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Coluna direita — 2fr (3 Fases + Recomendação + Oportunidade) */}
        <div className="lg:col-span-2 space-y-6">
          {/* 3 Fases do Atendimento */}
          {Object.keys(fases).length > 0 ? (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <FileText size={20} className="text-primary" />
                <h3 className="font-bold text-lg text-textMain">Avaliação em 3 Fases</h3>
              </div>
              <div className="space-y-4">
                <PhaseCard
                  title="1. Início — Apresentação e Acolhimento"
                  icon={null}
                  fase={faseInicio}
                />
                <PhaseCard
                  title="2. Meio — Métodos de Resolução"
                  icon={null}
                  fase={faseMeio}
                />
                <PhaseCard
                  title="3. Fim — Fechamento e Alinhamento"
                  icon={null}
                  fase={faseFim}
                />
              </div>
            </div>
          ) : (
            !isErro && (
              <div className="glass-panel p-6 text-center">
                <FileText size={24} className="text-textMuted mx-auto mb-2" />
                <p className="text-sm text-textMuted">Análise por fases não disponível para esta chamada.</p>
              </div>
            )
          )}

          {/* Transcrição (collapsible) — abaixo da Avaliação 3 Fases na direita */}
          {call?.transcricao_diarizada && (
            <div className="glass-panel p-5">
              <button
                onClick={() => setShowTranscript(!showTranscript)}
                className="flex items-center justify-between w-full"
              >
                <div className="flex items-center gap-2">
                  <MessageSquare size={18} className="text-textMuted" />
                  <h3 className="font-semibold text-textMain">Transcrição</h3>
                </div>
                {showTranscript ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
              </button>

              {showTranscript && (
                <div className="mt-4 pt-4 border-t border-black/5 space-y-3 max-h-[500px] overflow-y-auto">
                  {call.transcricao_diarizada.split('\n\n').map((block, i) => {
                    const isOp = block.toLowerCase().startsWith('operador:')
                    const isClient = block.toLowerCase().startsWith('cliente:')
                    if (!block.trim()) return null
                    let textContent = block
                    if (isOp) textContent = block.substring(9).trim()
                    if (isClient) textContent = block.substring(8).trim()
                    return (
                      <div key={i} className={`flex gap-3 ${isOp ? 'flex-row' : 'flex-row-reverse'}`}>
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                          isOp ? 'bg-primary text-white' : 'bg-surface text-textMuted border border-black/10'
                        }`}>
                          {isOp ? <Headphones size={14} /> : <User size={14} />}
                        </div>
                        <div className={`p-3 rounded-2xl max-w-[85%] text-sm leading-relaxed ${
                          isOp ? 'bg-surface border border-black/5 text-textMain rounded-tl-sm'
                               : 'bg-black/5 text-textMain rounded-tr-sm'
                        }`}>
                          {textContent}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* Recomendação de Treinamento (coluna direita, abaixo da Transcrição) */}
          {analysis?.recomendacao_treinamento && (
            <div className="glass-panel p-5">
              <div className="flex items-center gap-2 mb-3">
                <MessageSquare size={18} className="text-primary" />
                <h3 className="font-semibold text-textMain">Recomendação de Treinamento</h3>
              </div>
              <p className="text-sm text-textMain leading-relaxed">{analysis.recomendacao_treinamento}</p>
            </div>
          )}

          {/* Oportunidade Comercial (coluna direita, abaixo da Recomendação) */}
          {analysis?.oportunidade_venda_retencao && (
            <div className={`glass-panel p-5 ${analysis.sucesso_venda_retencao ? 'border-green-500/30 bg-green-50/50' : 'border-yellow-500/30 bg-yellow-50/50'}`}>
              <div className="flex items-center gap-2 mb-4">
                <ThumbsUp size={18} className={analysis.sucesso_venda_retencao ? 'text-green-600' : 'text-yellow-600'} />
                <h3 className="font-semibold text-textMain">
                  {analysis.tipo_oportunidade || 'Oportunidade de Venda/Retenção'}
                </h3>
              </div>
              <div className="text-sm font-medium text-textMain mb-3">
                Sucesso na conversão?{' '}
                <span className={`ml-2 px-2 py-0.5 rounded-full text-xs ${analysis.sucesso_venda_retencao ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                  {analysis.sucesso_venda_retencao ? 'Sim' : 'Não'}
                </span>
              </div>
              {Array.isArray(analysis?.argumentos_operador) && analysis.argumentos_operador.length > 0 && (
                <div>
                  <div className="text-xs font-bold text-textMuted uppercase mb-2">Argumentos Utilizados</div>
                  <ul className="space-y-1">
                    {analysis.argumentos_operador.map((arg, i) => (
                      <li key={i} className="text-sm text-textMain flex items-start gap-2">
                        <span className="text-primary shrink-0">•</span> {arg}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>


      {/* Player de Áudio — abaixo do grid */}
      <div id="audio-player">
        {audioUrl ? (
          <div className="bg-primary/5 p-4 rounded-2xl border border-primary/20 shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <Headphones size={16} className="text-primary" />
              <span className="font-bold text-sm text-textMain">Gravação da Chamada</span>
            </div>
            <audio controls className="w-full h-10 outline-none" src={audioUrl} />
          </div>
        ) : audioError ? (
          <div className="bg-yellow-50 border border-yellow-200 p-4 rounded-2xl text-sm text-yellow-800 flex items-start gap-3">
            <AlertTriangle size={18} className="shrink-0 mt-0.5 text-yellow-600" />
            <div>
              <span className="font-semibold">{audioError}</span>
              <p className="text-yellow-700/70 mt-1">A transcricao e avaliacao continuam disponiveis abaixo.</p>
            </div>
          </div>
        ) : null}
      </div>

    </div>
  )
}
