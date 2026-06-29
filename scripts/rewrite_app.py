import os

APP_PATH = "frontend/src/App.jsx"

NEW_APP = """import { useState, useEffect } from 'react'
import { Headphones, LogOut } from 'lucide-react'
import Dashboard from './components/Dashboard'
import CallInspector from './components/CallInspector'
import { GoogleLogin, googleLogout } from '@react-oauth/google'
import axios from 'axios'

function App() {
  const [selectedCall, setSelectedCall] = useState(null)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-cx-4105010761.us-central1.run.app"

  useEffect(() => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      axios.get(`${API_URL}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      }).then(res => {
        setUser(res.data)
      }).catch(err => {
        console.error("Token expirado ou inválido", err)
        localStorage.removeItem('auth_token')
      }).finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [API_URL])

  const handleLoginSuccess = (credentialResponse) => {
    const token = credentialResponse.credential
    localStorage.setItem('auth_token', token)
    axios.get(`${API_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` }
    }).then(res => {
      setUser(res.data)
    }).catch(err => {
      console.error(err)
    })
  }

  const handleLogout = () => {
    googleLogout()
    localStorage.removeItem('auth_token')
    setUser(null)
  }

  if (loading) return <div className="min-h-screen flex items-center justify-center bg-background">Carregando...</div>

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="glass-panel p-8 max-w-md w-full text-center space-y-6">
          <div className="flex justify-center mb-4">
            <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center">
              <Headphones className="text-primary" size={32} />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-textMain">Monitoria CX</h1>
          <p className="text-textMuted mb-8">Faça login para acessar o painel de auditoria por IA.</p>
          <div className="flex justify-center">
            <GoogleLogin
              onSuccess={handleLoginSuccess}
              onError={() => console.log('Login Failed')}
              useOneTap
            />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="border-b border-black/10 bg-surface/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div 
            className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
            onClick={() => setSelectedCall(null)}
          >
            <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
              <Headphones className="text-white" size={18} />
            </div>
            <h1 className="text-lg font-bold text-textMain tracking-tight">Monitoria CX</h1>
          </div>
          
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              {user.picture && <img src={user.picture} alt="User" className="w-8 h-8 rounded-full" />}
              <span className="text-sm font-medium text-textMain hidden sm:block">{user.name}</span>
            </div>
            <button onClick={handleLogout} className="text-textMuted hover:text-textMain transition-colors">
              <LogOut size={20} />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl mx-auto w-full p-4 sm:p-6 lg:p-8">
        {selectedCall ? (
          <CallInspector 
            callId={selectedCall} 
            onBack={() => setSelectedCall(null)} 
          />
        ) : (
          <Dashboard onSelectCall={setSelectedCall} />
        )}
      </main>
    </div>
  )
}

export default App
"""

with open(APP_PATH, "w", encoding="utf-8") as f:
    f.write(NEW_APP)

print("App.jsx reescrito!")
