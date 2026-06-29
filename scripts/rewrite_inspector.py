import os

INSP_PATH = "frontend/src/components/CallInspector.jsx"

NEW_INSP = """import { useState, useEffect } from 'react'
import { ArrowLeft, User, Headphones, CheckCircle2, AlertTriangle, MessageSquare, ThumbsUp, HelpCircle, ShieldAlert } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-cx-4105010761.us-central1.run.app"

export default function CallInspector({ callId, onBack }) {
  const [call, setCall] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

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
        
        {/* Coluna Esquerda: Transcrição */}
        <div className="lg:col-span-2 glass-panel p-6">
          <h3 className="font-semibold text-textMain mb-6 flex items-center gap-2">
            <MessageSquare size={18} className="text-primary" />
            Transcrição Diarizada
          </h3>
          <div className="space-y-4 max-h-[600px] overflow-y-auto pr-4 scrollbar-thin">
            {call.transcricao_diarizada ? call.transcricao_diarizada.split('\\n\\n').map((block, i) => {
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
        </div>

        {/* Coluna Direita: Analise */}
        <div className="space-y-6">
          
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
              {call.sentimentos_operador?.map((s, i) => (
                <span key={i} className="bg-surface text-textMain px-3 py-1 rounded-full text-sm font-medium border border-black/10">
                  {s}
                </span>
              ))}
            </div>
          </div>

          <div className="glass-panel p-6">
            <h3 className="font-semibold text-textMain mb-4 flex items-center gap-2">
              <User size={18} className="text-textMuted" />
              Sentimentos (Cliente)
            </h3>
            <div className="flex flex-wrap gap-2">
              {call.sentimentos_cliente?.map((s, i) => (
                <span key={i} className="bg-surface text-textMain px-3 py-1 rounded-full text-sm font-medium border border-black/10">
                  {s}
                </span>
              ))}
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
"""

with open(INSP_PATH, "w", encoding="utf-8") as f:
    f.write(NEW_INSP)
print("CallInspector atualizado!")
