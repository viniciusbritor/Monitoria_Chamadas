import { useState, useEffect, useRef } from 'react'
import { Upload, Headphones, Loader2, CheckCircle, XCircle, Search } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-test-env-894828119087.us-central1.run.app"

// Polling adaptativo: 2s quando ha chamada processando, 10s quando idle.
// Reduz latencia percebida sem sobrecarregar API quando nao ha atividade.
const POLL_ACTIVE_MS = 2000
const POLL_IDLE_MS = 10000

export default function Dashboard({ onInspectCall }) {
  const [calls, setCalls] = useState([])
  const [uploading, setUploading] = useState(false)
  const [diretrizes, setDiretrizes] = useState("")
  const intervalRef = useRef(null)

  const fetchCalls = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      const res = await axios.get(`${API_URL}/api/calls`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setCalls(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  // NEW (05/07/2026): polling adaptativo.
  // Detecta se ha chamada em processamento e ajusta o intervalo.
  const hasActiveCall = calls.some(
    (c) => c.status !== 'Concluído' && !String(c.status || '').startsWith('Erro')
  )
  const pollMs = hasActiveCall ? POLL_ACTIVE_MS : POLL_IDLE_MS

  useEffect(() => {
    fetchCalls()
    if (intervalRef.current) clearInterval(intervalRef.current)
    intervalRef.current = setInterval(fetchCalls, pollMs)
    return () => clearInterval(intervalRef.current)
  }, [pollMs])

  const calculateRetentionStats = () => {
    let opportunities = 0;
    let successes = 0;
    calls.forEach(call => {
      if (call.raw_evaluation) {
        try {
          const evalData = typeof call.raw_evaluation === 'string' ? JSON.parse(call.raw_evaluation) : call.raw_evaluation;
          if (evalData.oportunidade_venda_retencao) opportunities++;
          if (evalData.sucesso_venda_retencao) successes++;
        } catch (e) {}
      }
    });
    return { opportunities, successes };
  }

  const { opportunities, successes } = calculateRetentionStats();

  const handleFileUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    formData.append('diretrizes', diretrizes)
    
    try {
      const token = localStorage.getItem('auth_token')
      await axios.post(`${API_URL}/api/upload`, formData, {
        headers: { Authorization: `Bearer ${token}` }
      })
      fetchCalls()
      setDiretrizes("") // limpa após upload
    } catch (err) {
      alert('Erro no upload')
    } finally {
      setUploading(false)
      e.target.value = null
    }
  }

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Upload Card */}
        <div className="glass-panel p-6 flex flex-col items-center justify-center text-center space-y-4 md:col-span-1">
          <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center">
            <Upload className="text-primary" size={24} />
          </div>
          <div>
            <h3 className="font-semibold text-textMain">Nova Monitoria</h3>
            <p className="text-sm text-textMuted mt-1">Faça upload de áudio (MP3/WAV/MPEG)</p>
          </div>
          
          <div className="w-full text-left mt-2">
            <label className="text-xs font-semibold text-textMuted uppercase mb-1 block">Diretrizes (Opcional)</label>
            <textarea 
              value={diretrizes}
              onChange={(e) => setDiretrizes(e.target.value)}
              placeholder="Ex: O operador deve oferecer o seguro de vida."
              className="w-full text-sm bg-background border border-black/10 rounded-lg p-2 text-textMain focus:outline-none focus:border-primary resize-none h-16"
            />
          </div>

          <label className={`w-full py-3 px-4 rounded-xl font-medium transition-all cursor-pointer flex items-center justify-center gap-2 ${uploading ? 'bg-black/5 text-textMuted' : 'bg-primary hover:bg-primary/90 text-white'}`}>
            {uploading ? (
              <><Loader2 className="animate-spin" size={18} /> Processando...</>
            ) : (
              <>Selecionar Arquivo</>
            )}
            <input type="file" className="hidden" accept="audio/*,video/mpeg,video/mp4,.mpeg,.mp4,.wav,.mp3" onChange={handleFileUpload} disabled={uploading} />
          </label>
        </div>

        {/* Stats */}
        <div className="glass-panel p-6 flex flex-col justify-center md:col-span-2">
          <h3 className="font-semibold text-textMain mb-6">Visão Geral</h3>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-background rounded-xl p-4 border border-black/5">
              <div className="text-sm text-textMuted mb-1">Chamadas</div>
              <div className="text-2xl font-bold text-textMain">{calls.length}</div>
            </div>
            <div className="bg-background rounded-xl p-4 border border-black/5">
              <div className="text-sm text-textMuted mb-1">Média QA</div>
              <div className="text-2xl font-bold text-primary">
                {calls.length ? Math.round(calls.reduce((a,b) => a + (b.nota_qualidade_operador||0), 0) / calls.length) : 0}
              </div>
            </div>
            <div className="bg-background rounded-xl p-4 border border-black/5">
              <div className="text-sm text-textMuted mb-1">NPS Médio</div>
              <div className="text-2xl font-bold text-green-500">
                {calls.length ? (calls.reduce((a,b) => a + (b.nota_sentimento_cliente||0), 0) / calls.length).toFixed(1) : 0}
              </div>
            </div>
            <div className="bg-green-50/50 rounded-xl p-4 border border-green-500/20">
              <div className="text-sm text-green-800 font-medium mb-1">Vendas / Retenção</div>
              <div className="text-2xl font-bold text-green-600">
                {successes} <span className="text-sm text-green-700/60 font-medium">/ {opportunities} op.</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Tabela de Chamadas */}
      <div className="glass-panel overflow-hidden">
        <div className="p-6 border-b border-black/5 flex items-center justify-between">
          <h3 className="font-semibold text-textMain">Últimas Monitorias</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-background text-textMuted text-sm">
                <th className="p-4 font-medium">Arquivo</th>
                <th className="p-4 font-medium">Data</th>
                <th className="p-4 font-medium">Status</th>
                <th className="p-4 font-medium">QA (Op.)</th>
                <th className="p-4 font-medium">Cliente</th>
                <th className="p-4 font-medium text-right">Ação</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((call) => (
                <tr key={call.id} className="border-b border-black/5 hover:bg-black/5 transition-colors">
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                        <Headphones className="text-primary" size={16} />
                      </div>
                      <span className="font-medium text-textMain max-w-[150px] truncate">{call.filename}</span>
                    </div>
                  </td>
                  <td className="p-4 text-sm text-textMuted">
                    {new Date(call.uploaded_at).toLocaleString('pt-BR')}
                  </td>
                  <td className="p-4">
                    <div className="flex flex-col gap-1.5">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-background border border-black/10 text-textMain w-fit">
                        {call.status === 'Concluído' ? <CheckCircle size={12} className="text-green-500" /> :
                         call.status.startsWith('Erro') ? <XCircle size={12} className="text-red-500" /> :
                         <Loader2 size={12} className="text-primary animate-spin" />}
                        {call.status}
                      </span>
                      {call.status !== 'Concluído' && !call.status.startsWith('Erro') && (() => {
                        // Progresso real: backend retorna progress_pct (0-100) na fase Whisper.
                        // Fases Diarizacao/Analise nao tem % -> fallback indeterminada.
                        const pct = typeof call.progress_pct === 'number' ? call.progress_pct : 0
                        const hasRealProgress = pct > 0 && String(call.status).toLowerCase().includes('whisper')
                        const widthStyle = hasRealProgress
                          ? { width: `${Math.min(100, pct)}%`, transition: 'width 600ms ease-out' }
                          : undefined
                        return (
                          <>
                            <div className="flex items-center gap-2">
                              <div
                                className="w-[180px] h-[3px] bg-black/5 rounded-full overflow-hidden"
                                role="progressbar"
                                aria-label="Progresso do processamento"
                                aria-valuemin={0}
                                aria-valuemax={100}
                                aria-valuenow={hasRealProgress ? Math.round(pct) : undefined}
                                aria-valuetext={call.status}
                              >
                                <div
                                  className={`h-full bg-primary rounded-full ${hasRealProgress ? '' : 'w-1/3 animate-progress'}`}
                                  style={widthStyle}
                                />
                              </div>
                              {hasRealProgress && (
                                <span className="text-[10px] text-textMuted font-medium tabular-nums">
                                  {Math.round(pct)}%
                                </span>
                              )}
                            </div>
                            <span className="text-[10px] text-textMuted ml-1 animate-pulse">
                              Tempo estimado: ~3-5 min (audio curto) / ate 25 min (audio longo)
                            </span>
                          </>
                        )
                      })()}
                    </div>
                  </td>
                  <td className="p-4">
                    {call.status === 'Concluído' && (
                      <span className="font-bold text-textMain">{call.nota_qualidade_operador||call.nota}</span>
                    )}
                  </td>
                  <td className="p-4">
                    {call.status === 'Concluído' && (
                      <span className="font-bold text-green-600">{call.nota_sentimento_cliente||0}/10</span>
                    )}
                  </td>
                  <td className="p-4 text-right">
                    <button 
                      onClick={() => call.status === 'Concluído' && onInspectCall(call.id)}
                      disabled={call.status !== 'Concluído'}
                      className="text-primary hover:text-primary/80 font-medium text-sm disabled:opacity-30 transition-colors"
                    >
                      Inspecionar
                    </button>
                  </td>
                </tr>
              ))}
              {calls.length === 0 && (
                <tr>
                  <td colSpan="6" className="p-8 text-center text-textMuted">Nenhuma chamada processada ainda.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
