import { useState, useEffect } from 'react'
import {
  ArrowLeft, CheckCircle2, AlertTriangle, ThumbsUp,
  ShieldAlert, ChevronDown, ChevronUp, Headphones, User,
  FileText, Brain, Star, MessageSquare, Target
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

function PhaseCard({ title, icon: Icon, fase }) {
  const qa = fase?.nota_qa || 0
  const nps = fase?.nota_nps || 0
  return (
    <div className="p-5 rounded-2xl bg-surface border border-black/5 space-y-3 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {Icon && <Icon size={20} className="text-primary shrink-0" />}
          <h4 className="font-bold text-textMain text-base">{title}</h4>
        </div>
        <div className="flex gap-2 text-xs shrink-0">
          <ScoreBadge value={qa} max={100} />
          <ScoreBadge value={nps} max={10} />
        </div>
      </div>
      <p className="text-sm text-textMuted leading-relaxed">
        {fase?.analise || "Análise não disponível para esta fase."}
      </p>
    </div>
  )
}

function TagList({ items, emptyText = "Nenhum item" }) {
  if (!Array.isArray(items) || items.length === 0) {
    return <span className="text-xs text-textMuted italic">{emptyText}</span>
  }
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item, i) => (
        <span key={i} className="bg-surface text-textMain px-3 py-1 rounded-full text-sm font-medium border border-black/10">
          {item}
        </span>
      ))}
    </div>
  )
}

export default function CallInspector({ callId, onBack }) {
  const [call, setCall] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showTranscript, setShowTranscript] = useState(false)
  const [audioUrl, setAudioUrl] = useState(null)

  useEffect(() => {
    let cancelled = false
    const fetchCall = async () => {
      try {
        const token = localStorage.getItem('auth_token')
        const res = await axios.get(`${API_URL}/api/calls/${callId}`, {
          headers: { Authorization: `Bearer ${token}` }
        })

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
        } catch (_) {}
      } catch (err) {
        if (!cancelled) {
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
    <div className="space-y-8 max-w-4xl mx-auto">

      {/* Cabeçalho */}
      <div className="flex items-center gap-4">
        <button onClick={onBack} className="p-2 bg-surface hover:bg-black/10 rounded-xl transition-colors shrink-0">
          <ArrowLeft size={20} />
        </button>
        <div className="min-w-0">
          <h2 className="text-xl font-bold text-textMain truncate">{filename}</h2>
          <div className="text-sm text-textMuted mt-1 flex items-center gap-3 flex-wrap">
            <span>{uploadedAt.toLocaleString('pt-BR')}</span>
            {iaUtilizada !== 'IA' && (
              <span className="text-xs bg-black/5 px-2 py-0.5 rounded-full">
                IA: {iaUtilizada}
              </span>
            )}
          </div>
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

      {/* Player de Áudio */}
      {audioUrl && (
        <div className="bg-surface p-4 rounded-2xl border border-black/5 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <Headphones size={16} className="text-primary" />
            <span className="font-bold text-sm text-textMain">Gravacao da Chamada</span>
          </div>
          <audio controls className="w-full h-10 outline-none" src={audioUrl} />
        </div>
      )}

      {/* Score Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
        <div className="glass-panel p-5 text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <Brain size={18} className="text-purple-500" />
            <h3 className="font-medium text-textMuted text-xs uppercase tracking-wide">IA Utilizada</h3>
          </div>
          <div className="text-xl font-bold text-purple-600">{iaUtilizada}</div>
        </div>
      </div>

      {/* 3 Fases do Atendimento */}
      {Object.keys(fases).length > 0 ? (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <FileText size={20} className="text-primary" />
            <h3 className="font-bold text-lg text-textMain">Avaliacao em 3 Fases</h3>
          </div>
          <div className="space-y-4">
            <PhaseCard
              title="1. Inicio — Apresentacao e Acolhimento"
              icon={null}
              fase={faseInicio}
            />
            <PhaseCard
              title="2. Meio — Metodos de Resolucao"
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
            <p className="text-sm text-textMuted">Analise por fases nao disponivel para esta chamada.</p>
          </div>
        )
      )}

      {/* Humor / Sentimentos */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="glass-panel p-5">
          <div className="flex items-center gap-2 mb-4">
            <User size={18} className="text-textMuted" />
            <h3 className="font-semibold text-textMain">Humor do Cliente</h3>
          </div>
          <TagList
            items={analysis?.sentimentos_cliente || []}
            emptyText="Nenhum sentimento detectado"
          />
          {analysis?.humor_cliente && (
            <div className="mt-3">
              <span className="text-xs text-textMuted">Classificacao: </span>
              <span className="text-sm font-medium text-textMain">{analysis.humor_cliente}</span>
            </div>
          )}
        </div>
        <div className="glass-panel p-5">
          <div className="flex items-center gap-2 mb-4">
            <Headphones size={18} className="text-primary" />
            <h3 className="font-semibold text-textMain">Humor do Atendente</h3>
          </div>
          <TagList
            items={analysis?.sentimentos_operador || []}
            emptyText="Nenhum sentimento detectado"
          />
          {analysis?.humor_expert && (
            <div className="mt-3">
              <span className="text-xs text-textMuted">Classificacao: </span>
              <span className="text-sm font-medium text-textMain">{analysis.humor_expert}</span>
            </div>
          )}
        </div>
      </div>

      {/* Erro Crítico */}
      <div className={`glass-panel p-5 ${analysis?.erro_critico ? 'border-red-500/30 bg-red-50/80' : ''}`}>
        <div className="flex items-center gap-3">
          <ShieldAlert size={20} className={analysis?.erro_critico ? 'text-red-500' : 'text-green-500'} />
          <div>
            <h3 className="font-semibold text-textMain">Erro Critico</h3>
            <p className={`text-sm font-medium mt-1 ${analysis?.erro_critico ? 'text-red-600' : 'text-green-600'}`}>
              {analysis?.erro_critico ? 'SIM — Foram identificados erros fatais no atendimento' : 'NAO — Nenhum erro fatal identificado'}
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

      {/* Recomendação de Treinamento */}
      {analysis?.recomendacao_treinamento && (
        <div className="glass-panel p-5">
          <div className="flex items-center gap-2 mb-3">
            <MessageSquare size={18} className="text-primary" />
            <h3 className="font-semibold text-textMain">Recomendacao de Treinamento</h3>
          </div>
          <p className="text-sm text-textMain leading-relaxed">{analysis.recomendacao_treinamento}</p>
        </div>
      )}

      {/* Oportunidade Comercial */}
      {analysis?.oportunidade_venda_retencao && (
        <div className={`glass-panel p-5 ${analysis.sucesso_venda_retencao ? 'border-green-500/30 bg-green-50/50' : 'border-yellow-500/30 bg-yellow-50/50'}`}>
          <div className="flex items-center gap-2 mb-4">
            <ThumbsUp size={18} className={analysis.sucesso_venda_retencao ? 'text-green-600' : 'text-yellow-600'} />
            <h3 className="font-semibold text-textMain">
              {analysis.tipo_oportunidade || 'Oportunidade de Venda/Retencao'}
            </h3>
          </div>
          <div className="text-sm font-medium text-textMain mb-3">
            Sucesso na conversao?{' '}
            <span className={`ml-2 px-2 py-0.5 rounded-full text-xs ${analysis.sucesso_venda_retencao ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
              {analysis.sucesso_venda_retencao ? 'Sim' : 'Nao'}
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

      {/* Transcrição Diarizada (Collapsible) */}
      <div className="glass-panel p-5">
        <button
          onClick={() => setShowTranscript(!showTranscript)}
          className="flex items-center justify-between w-full"
        >
          <div className="flex items-center gap-2">
            <MessageSquare size={18} className="text-textMuted" />
            <h3 className="font-semibold text-textMain">Transcricao Diarizada</h3>
          </div>
          {showTranscript ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
        </button>

        {showTranscript && (
          <div className="mt-4 pt-4 border-t border-black/5 space-y-3 max-h-[500px] overflow-y-auto">
            {(call && call.transcricao_diarizada) ? (
              call.transcricao_diarizada.split('\n\n').map((block, i) => {
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
              })
            ) : (
              <p className="text-sm text-textMuted italic text-center py-4">
                Transcricao diarizada nao disponivel para esta chamada.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Pontos Positivos e Melhoria */}
      {(analysis?.pontos_positivos?.length > 0 || analysis?.pontos_melhoria?.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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
      )}

    </div>
  )
}
