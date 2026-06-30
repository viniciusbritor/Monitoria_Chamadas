import { useState, useEffect } from 'react'
import { Save, Plus, Trash2, CheckCircle2, ShieldAlert, Loader2 } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-cx-4105010761.us-central1.run.app"

export default function SettingsPanel() {
  const [checklist, setChecklist] = useState(["Saudação inicial", "Validação de dados"])
  const [newItem, setNewItem] = useState("")
  const [estrategiaVendas, setEstrategiaVendas] = useState("")
  const [estrategiaRetencao, setEstrategiaRetencao] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    fetchSettings()
  }, [])

  const fetchSettings = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      const res = await axios.get(`${API_URL}/api/settings`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.data) {
        setChecklist(JSON.parse(res.data.checklist_items || "[]"))
        setEstrategiaVendas(res.data.estrategia_vendas || "")
        setEstrategiaRetencao(res.data.estrategia_retencao || "")
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const token = localStorage.getItem('auth_token')
      await axios.post(`${API_URL}/api/settings`, {
        checklist_items: JSON.stringify(checklist),
        estrategia_vendas: estrategiaVendas,
        estrategia_retencao: estrategiaRetencao
      }, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setMessage({ type: 'success', text: 'Configurações salvas com sucesso!' })
    } catch (err) {
      setMessage({ type: 'error', text: 'Erro ao salvar configurações.' })
    } finally {
      setSaving(false)
      setTimeout(() => setMessage(null), 3000)
    }
  }

  const handleAddItem = (e) => {
    e.preventDefault()
    if (!newItem.trim()) return
    setChecklist([...checklist, newItem.trim()])
    setNewItem("")
  }

  const handleRemoveItem = (index) => {
    setChecklist(checklist.filter((_, i) => i !== index))
  }

  if (loading) return <div className="text-center py-12 text-textMuted flex items-center justify-center gap-2"><Loader2 className="animate-spin" /> Carregando...</div>

  return (
    <div className="space-y-6 animate-in slide-in-from-right-8 duration-500 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-textMain">Configurações de IA</h2>
          <p className="text-textMuted mt-1 text-sm">Parametrize o Checklist de Auditoria e os Playbooks de Geração de Valor.</p>
        </div>
        <button 
          onClick={handleSave} 
          disabled={saving}
          className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-white px-6 py-2.5 rounded-xl font-medium transition-all"
        >
          {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
          Salvar Alterações
        </button>
      </div>

      {message && (
        <div className={`p-4 rounded-xl flex items-center gap-3 ${message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
          {message.type === 'success' ? <CheckCircle2 size={18} /> : <ShieldAlert size={18} />}
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Checklist Column */}
        <div className="glass-panel p-6">
          <h3 className="font-semibold text-textMain mb-2 flex items-center gap-2">
            <CheckCircle2 size={18} className="text-primary" />
            Checklist Padrão
          </h3>
          <p className="text-xs text-textMuted mb-6">Lista de ações obrigatórias que a IA deverá auditar em todas as chamadas.</p>

          <form onSubmit={handleAddItem} className="flex gap-2 mb-6">
            <input 
              type="text" 
              value={newItem}
              onChange={(e) => setNewItem(e.target.value)}
              placeholder="Ex: Confirmação de Segurança (CPF)"
              className="flex-1 bg-background border border-black/10 rounded-lg p-2.5 text-sm text-textMain focus:outline-none focus:border-primary"
            />
            <button type="submit" className="bg-surface border border-black/10 hover:bg-black/5 p-2.5 rounded-lg text-textMain transition-colors">
              <Plus size={20} />
            </button>
          </form>

          <div className="space-y-3">
            {checklist.map((item, i) => (
              <div key={i} className="flex items-center justify-between p-3 bg-background border border-black/5 rounded-xl">
                <span className="text-sm font-medium text-textMain">{item}</span>
                <button onClick={() => handleRemoveItem(i)} className="text-red-500 hover:bg-red-50 p-1.5 rounded-lg transition-colors">
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
            {checklist.length === 0 && (
              <div className="text-sm text-textMuted italic text-center py-4">Nenhum item cadastrado.</div>
            )}
          </div>
        </div>

        {/* Estratégias Column */}
        <div className="space-y-6">
          <div className="glass-panel p-6">
            <h3 className="font-semibold text-textMain mb-2 text-green-700">Playbook de Vendas</h3>
            <p className="text-xs text-textMuted mb-4">Como a IA deve auditar uma oportunidade de venda? (Up-sell / Cross-sell)</p>
            <textarea 
              value={estrategiaVendas}
              onChange={(e) => setEstrategiaVendas(e.target.value)}
              placeholder="Ex: Se for venda, oferecer sempre o produto Premium. Cross-sell: sempre tentar acoplar o serviço Básico se comprar o Avançado..."
              className="w-full h-32 bg-background border border-black/10 rounded-xl p-3 text-sm text-textMain focus:outline-none focus:border-green-500 resize-none"
            />
          </div>

          <div className="glass-panel p-6">
            <h3 className="font-semibold text-textMain mb-2 text-yellow-700">Playbook de Retenção</h3>
            <p className="text-xs text-textMuted mb-4">Como a IA deve auditar um pedido de cancelamento?</p>
            <textarea 
              value={estrategiaRetencao}
              onChange={(e) => setEstrategiaRetencao(e.target.value)}
              placeholder="Ex: Oferecer primeiro um desconto de 10%. Se o cliente insistir, tentar migrar para o plano Essencial..."
              className="w-full h-32 bg-background border border-black/10 rounded-xl p-3 text-sm text-textMain focus:outline-none focus:border-yellow-500 resize-none"
            />
          </div>
        </div>
      </div>
    </div>
  )
}
