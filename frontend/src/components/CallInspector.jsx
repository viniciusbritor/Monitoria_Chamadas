import { useState, useEffect } from 'react'
import { ArrowLeft, User, Headphones, CheckCircle2, AlertTriangle, MessageSquare, ThumbsUp, HelpCircle, ShieldAlert } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-cx-4105010761.us-central1.run.app"

export default function CallInspector({ callId, onBack }) {
  const [call, setCall] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('report') // 'report' | 'transcript'

  useEffect(() => {
    const fetchCall = async () => {
      try {
        const token = localStorage.getItem('auth_token')
        const res = await axios.get(`${API_URL}/api/calls/${callId}`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        
        let analysisData = res.data.raw_evaluation
        if (typeof analysisData === 'string') analysisData = JSON.parse(analysisData)
          
        setCall({ ...res.data, analysis: analysisData })
      } catch (err) {
        setError('Erro ao carregar detalhes')
      } finally {
        setLoading(false)
      }
    }
    fetchCall()
  }, [callId])

  if (loading) return <div className="text-center py-12 text-textMuted">Carregando análise...</div>
  if (error || !call) return <div className="text-center py-12 text-red-400">{error}</div>

  const qaScore = call.nota_qualidade_operador || call.nota || 0
  const clientScore = call.nota_sentimento_cliente || 0

  return (
    <div className="space-y-6 animate-in slide-in-from-right-8 duration-500">
      
      {/* Top Bar */}
      <div className="flex items-center gap-4 mb-8">
        <button onClick={onBack} className="p-2 bg-surface hover:bg-black/10 rounded-xl transition-colors">
          <ArrowLeft size={20} />
        </button>
        <div>
          <h2 className="text-xl font-bold text-textMain">{call.filename}</h2>
          <div className="text-sm text-textMuted mt-1">
            Data: {new Date(call.uploaded_at).toLocaleString('pt-BR')}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Coluna Esquerda: Relatório de Monitoria e Transcrição */}
        <div className="lg:col-span-2 glass-panel p-6 flex flex-col">
          <div className="flex items-center justify-between border-b border-black/10 pb-4 mb-6">
            <div className="flex gap-4">
              <button 
                onClick={() => setActiveTab('report')}
                className={`pb-2 text-sm font-bold border-b-2 transition-all ${activeTab === 'report' ? 'border-primary text-primary' : 'border-transparent text-textMuted hover:text-textMain'}`}
              >
                Relatório de Monitoria (3 Fases)
              </button>
              <button 
                onClick={() => setActiveTab('transcript')}
                className={`pb-2 text-sm font-bold border-b-2 transition-all ${activeTab === 'transcript' ? 'border-primary text-primary' : 'border-transparent text-textMuted hover:text-textMain'}`}
              >
                Transcrição Diarizada
              </button>
            </div>
          </div>

          <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2 scrollbar-thin">
            {activeTab === 'report' && (
              <div className="space-y-6">
                {call.analysis?.fases ? (
                  ['apresentacao', 'resolucao', 'fechamento'].map((faseKey) => {
                    const titles = {
                      apresentacao: "1. Apresentação (Acolhimento e Entendimento)",
                      resolucao: "2. Métodos de Resolução (Ações de Solução)",
                      fechamento: "3. Fechamento da Chamada (Alinhamento de Trâmites)"
                    };
                    const fase = call.analysis.fases[faseKey] || {};
                    const qa = fase.nota_qa || 0;
                    const nps = fase.nota_nps || 0;
                    
                    return (
                      <div key={faseKey} className="p-5 rounded-2xl bg-surface border border-black/5 space-y-3 shadow-sm hover:shadow-md transition-shadow">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                          <h4 className="font-bold text-textMain text-base">{titles[faseKey]}</h4>
                          <div className="flex gap-2 text-xs">
                            <span className={`px-2.5 py-1 rounded-full font-bold ${qa >= 80 ? 'bg-green-50 text-green-700 border border-green-200' : qa >= 50 ? 'bg-yellow-50 text-yellow-700 border border-yellow-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
                              QA: {qa}/100
                            </span>
                            <span className={`px-2.5 py-1 rounded-full font-bold ${nps >= 8 ? 'bg-green-50 text-green-700 border border-green-200' : nps >= 5 ? 'bg-yellow-50 text-yellow-700 border border-yellow-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
                              NPS: {nps}/10
                            </span>
                          </div>
                        </div>
                        <p className="text-sm text-textMuted leading-relaxed">{fase.analise || "Nenhuma análise detalhada nesta fase."}</p>
                      </div>
                    )
                  })
                ) : (
                  <div className="text-sm text-textMuted italic py-6">
                    A análise detalhada por fases não está disponível para esta chamada antiga.
                  </div>
                )}
              </div>
            )}

            {activeTab === 'transcript' && (
              <div className="space-y-4">
                {call.transcricao_diarizada ? call.transcricao_diarizada.split('\n\n').map((block, i) => {
                  const isOp = block.toLowerCase().startsWith('operador:');
                  const isClient = block.toLowerCase().startsWith('cliente:');
                  if (!block.trim()) return null;
                  
                  let textContent = block;
                  if (isOp) textContent = block.substring(9).trim();
                  if (isClient) textContent = block.substring(8).trim();

                  return (
                    <div key={i} className={`flex gap-3 ${isOp ? 'flex-row' : 'flex-row-reverse'}`}>
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${isOp ? 'bg-primary text-white' : 'bg-surface text-textMuted border border-black/10'}`}>
                        {isOp ? <Headphones size={14} /> : <User size={14} />}
                      </div>
                      <div className={`p-3 rounded-2xl max-w-[85%] text-sm leading-relaxed ${isOp ? 'bg-surface border border-black/5 text-textMain rounded-tl-sm' : 'bg-black/5 text-textMain rounded-tr-sm'}`}>
                        {textContent}
                      </div>
                    </div>
                  )
                }) : (
                  <div className="text-sm text-textMuted italic">A transcrição diarizada não está disponível para esta chamada antiga.</div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Coluna Direita: Analise */}
        <div className="space-y-6">
          
          {call.analysis?.checklist_conformidade && (
            <div className="glass-panel p-6">
              <h3 className="font-semibold text-textMain mb-4 flex items-center gap-2">
                <CheckCircle2 size={18} className="text-primary" />
                Checklist de Conformidade
              </h3>
              <div className="space-y-3">
                {call.analysis.checklist_conformidade.map((item, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <div className="mt-0.5">
                      {item.cumprido ? (
                        <CheckCircle2 size={16} className="text-green-500" />
                      ) : (
                        <AlertTriangle size={16} className="text-red-500" />
                      )}
                    </div>
                    <span className={`text-sm leading-tight ${item.cumprido ? 'text-textMain' : 'text-red-600 font-medium'}`}>
                      {item.item}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {call.analysis?.oportunidade_venda_retencao && (
            <div className={`glass-panel p-6 ${call.analysis.sucesso_venda_retencao ? 'border-green-500/30 bg-green-50/50' : 'border-yellow-500/30 bg-yellow-50/50'}`}>
              <h3 className={`font-semibold mb-4 flex items-center gap-2 ${call.analysis.sucesso_venda_retencao ? 'text-green-700' : 'text-yellow-700'}`}>
                <ThumbsUp size={18} />
                {call.analysis.tipo_oportunidade || 'Oportunidade Comercial'}
              </h3>
              <div className="mb-4 text-sm font-medium text-textMain">
                Sucesso na conversão? 
                <span className={`ml-2 px-2 py-0.5 rounded-full ${call.analysis.sucesso_venda_retencao ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                  {call.analysis.sucesso_venda_retencao ? 'Sim' : 'Não'}
                </span>
              </div>
              {call.analysis.argumentos_operador && call.analysis.argumentos_operador.length > 0 && (
                <div>
                  <div className="text-xs font-bold text-textMuted uppercase mb-2">Argumentos Utilizados:</div>
                  <ul className="space-y-2">
                    {call.analysis.argumentos_operador.map((arg, i) => (
                      <li key={i} className="text-sm text-textMain flex items-start gap-2">
                        <span className="mt-1 text-primary flex-shrink-0">•</span> {arg}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="glass-panel p-6 flex items-center justify-between">
            <div>
              <h3 className="font-medium text-textMuted text-sm uppercase tracking-wide">QA Score (Operador)</h3>
              <div className="text-4xl font-black mt-2 text-textMain">
                <span className="text-primary">{qaScore}</span>
                <span className="text-xl text-textMuted">/100</span>
              </div>
            </div>
          </div>
          
          <div className="glass-panel p-6 flex items-center justify-between">
            <div>
              <h3 className="font-medium text-textMuted text-sm uppercase tracking-wide">Sentimento do Cliente</h3>
              <div className="text-4xl font-black mt-2 text-textMain">
                <span className="text-green-500">{clientScore}</span>
                <span className="text-xl text-textMuted">/10</span>
              </div>
            </div>
          </div>

          <div className="glass-panel p-6">
            <h3 className="font-semibold text-textMain mb-4 flex items-center gap-2">
              <Headphones size={18} className="text-primary" />
              Sentimentos (Operador)
            </h3>
            <div className="flex flex-wrap gap-2">
              {call.sentimentos_operador && call.sentimentos_operador.length > 0 ? (
                call.sentimentos_operador.map((s, i) => (
                  <span key={i} className="bg-surface text-textMain px-3 py-1 rounded-full text-sm font-medium border border-black/10">
                    {s}
                  </span>
                ))
              ) : (
                <span className="text-xs text-textMuted italic py-1">Nenhum sentimento detectado</span>
              )}
            </div>
          </div>

          <div className="glass-panel p-6">
            <h3 className="font-semibold text-textMain mb-4 flex items-center gap-2">
              <User size={18} className="text-textMuted" />
              Sentimentos (Cliente)
            </h3>
            <div className="flex flex-wrap gap-2">
              {call.sentimentos_cliente && call.sentimentos_cliente.length > 0 ? (
                call.sentimentos_cliente.map((s, i) => (
                  <span key={i} className="bg-surface text-textMain px-3 py-1 rounded-full text-sm font-medium border border-black/10">
                    {s}
                  </span>
                ))
              ) : (
                <span className="text-xs text-textMuted italic py-1">Nenhum sentimento detectado</span>
              )}
            </div>
          </div>
          
          {call.erros_fatais && call.erros_fatais.length > 0 && (
            <div className="glass-panel border-red-500/30 p-6 bg-red-50">
              <h3 className="font-semibold text-red-600 mb-4 flex items-center gap-2">
                <ShieldAlert size={18} />
                Erros Fatais
              </h3>
              <ul className="space-y-2">
                {call.erros_fatais.map((erro, i) => (
                  <li key={i} className="text-sm text-red-600 flex items-start gap-2">
                    <span className="mt-1 flex-shrink-0">•</span> {erro}
                  </li>
                ))}
              </ul>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
