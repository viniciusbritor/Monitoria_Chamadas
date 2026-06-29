import React, { useState, useEffect } from 'react'
import { ArrowLeft, UserPlus, UserCheck, ShieldAlert, Check, X, Shield } from 'lucide-react'

export default function AdminPanel({ onBack, userToken }) {
  const [users, setUsers] = useState([])
  const [newEmail, setNewEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(null)
  const [message, setMessage] = useState(null)

  const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-cx-4105010761.us-central1.run.app"

  const fetchUsers = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_URL}/api/admin/users`, {
        headers: { Authorization: `Bearer ${userToken}` }
      })
      if (res.ok) {
        const data = await res.json()
        setUsers(data)
      } else {
        console.error("Failed to fetch users")
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchUsers()
  }, [])

  const handleAddEmail = async (e) => {
    e.preventDefault()
    if (!newEmail.trim()) return
    setLoading(true)
    setMessage(null)
    try {
      const res = await fetch(`${API_URL}/api/admin/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${userToken}`
        },
        body: JSON.stringify({ email: newEmail.trim() })
      })
      if (res.ok) {
        const data = await res.json()
        setMessage({ type: 'success', text: data.message })
        setNewEmail('')
        fetchUsers()
      } else {
        const errData = await res.json()
        setMessage({ type: 'error', text: errData.detail || "Erro ao adicionar e-mail." })
      }
    } catch (err) {
      setMessage({ type: 'error', text: "Erro na requisição ao servidor." })
    } finally {
      setLoading(false)
    }
  }

  const handleToggleStatus = async (email, currentStatus) => {
    setActionLoading(email)
    setMessage(null)
    const endpoint = currentStatus ? 'revoke' : 'approve'
    try {
      const res = await fetch(`${API_URL}/api/admin/${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${userToken}`
        },
        body: JSON.stringify({ email })
      })
      if (res.ok) {
        fetchUsers()
      } else {
        const errData = await res.json()
        setMessage({ type: 'error', text: errData.detail || "Falha na ação." })
      }
    } catch (err) {
      setMessage({ type: 'error', text: "Erro ao se conectar ao servidor." })
    } finally {
      setActionLoading(null)
    }
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header do Admin */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <button 
            onClick={onBack}
            className="flex items-center gap-2 text-sm text-black/60 hover:text-black transition-colors mb-2"
          >
            <ArrowLeft size={16} />
            Voltar ao Dashboard
          </button>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Shield className="text-primary" />
            Gestão de Acessos
          </h1>
          <p className="text-black/60 text-sm mt-1">
            Gerencie e autorize e-mails para acesso à plataforma. Alterações entram em vigor imediatamente sem rebuild.
          </p>
        </div>
      </div>

      {/* Alertas */}
      {message && (
        <div className={`p-4 rounded-2xl border text-sm flex items-center gap-2 ${
          message.type === 'success' ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-800'
        }`}>
          {message.type === 'success' ? <UserCheck size={18} /> : <ShieldAlert size={18} />}
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Formulário de Adicionar E-mail */}
        <div className="glass-panel bg-white/70 backdrop-blur-xl p-6 rounded-3xl border border-black/5 shadow-lg space-y-4 h-fit">
          <h3 className="text-lg font-bold flex items-center gap-2">
            <UserPlus size={18} className="text-primary" />
            Autorizar Novo E-mail
          </h3>
          <form onSubmit={handleAddEmail} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-black/40 mb-2">E-mail do Usuário</label>
              <input 
                type="email" 
                placeholder="exemplo@gmail.com"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                required
                className="w-full bg-black/[0.02] border border-black/5 rounded-2xl px-4 py-3 text-sm focus:outline-none focus:border-primary/20 focus:bg-white transition-all"
              />
            </div>
            <button 
              type="submit" 
              disabled={loading}
              className="w-full bg-primary hover:bg-primary-hover text-white rounded-2xl py-3 text-sm font-semibold transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? 'Processando...' : 'Conceder Acesso'}
            </button>
          </form>
        </div>

        {/* Tabela de Usuários */}
        <div className="lg:col-span-2 glass-panel bg-white/70 backdrop-blur-xl p-6 rounded-3xl border border-black/5 shadow-lg space-y-4">
          <h3 className="text-lg font-bold">Usuários no Banco de Dados</h3>
          
          {loading && users.length === 0 ? (
            <div className="text-center py-8 text-black/40">Carregando lista de usuários...</div>
          ) : users.length === 0 ? (
            <div className="text-center py-8 text-black/40">Nenhum e-mail registrado.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-black/5 text-xs font-semibold uppercase tracking-wider text-black/40">
                    <th className="pb-3 pl-2">Usuário</th>
                    <th className="pb-3">Status</th>
                    <th className="pb-3 text-right pr-2">Ação</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 text-sm">
                  {users.map((u) => {
                    const isAdmin = u.email === "viniciusbritor@gmail.com" || u.email === "rafadesouzaoliveira@gmail.com"
                    return (
                      <tr key={u.id || u.email} className="hover:bg-black/[0.01] transition-colors">
                        <td className="py-4 pl-2 flex items-center gap-3">
                          {u.picture ? (
                            <img src={u.picture} alt="" className="w-8 h-8 rounded-full border border-black/5" />
                          ) : (
                            <div className="w-8 h-8 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center text-xs">
                              {(u.name || u.email).substring(0, 2).toUpperCase()}
                            </div>
                          )}
                          <div>
                            <div className="font-semibold text-black/90">{u.name || "Pendente de Login"}</div>
                            <div className="text-xs text-black/40">{u.email}</div>
                          </div>
                        </td>
                        <td className="py-4">
                          <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold ${
                            u.is_approved 
                              ? 'bg-green-50 text-green-700 border border-green-200/50' 
                              : 'bg-slate-50 text-slate-400 border border-slate-200/50'
                          }`}>
                            {u.is_approved ? (
                              <>
                                <Check size={12} />
                                Autorizado
                              </>
                            ) : (
                              <>
                                <X size={12} />
                                Sem Acesso
                              </>
                            )}
                          </span>
                        </td>
                        <td className="py-4 text-right pr-2">
                          {isAdmin ? (
                            <span className="text-xs font-semibold text-black/30 select-none pr-3">Admin</span>
                          ) : (
                            <button
                              disabled={actionLoading === u.email}
                              onClick={() => handleToggleStatus(u.email, u.is_approved)}
                              className={`text-xs font-semibold px-3 py-1.5 rounded-xl border transition-colors ${
                                u.is_approved 
                                  ? 'border-red-200 text-red-600 bg-red-50 hover:bg-red-100/50' 
                                  : 'border-green-200 text-green-700 bg-green-50 hover:bg-green-100/50'
                              }`}
                            >
                              {actionLoading === u.email ? 'Aguarde...' : u.is_approved ? 'Revogar' : 'Aprovar'}
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
