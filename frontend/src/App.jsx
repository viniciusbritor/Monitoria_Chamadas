import { useState, useEffect } from 'react'
import Dashboard from './components/Dashboard'
import CallInspector from './components/CallInspector'
import AdminPanel from './components/AdminPanel'
import SettingsPanel from './components/SettingsPanel'
import { Headphones, LogOut, Shield, Settings, Mail } from 'lucide-react'
import { auth, googleProvider, microsoftProvider, signInWithPopup } from './firebase'

function App() {
  const [currentView, setCurrentView] = useState('dashboard') // 'dashboard' | 'inspector' | 'admin' | 'settings'
  const [selectedCallId, setSelectedCallId] = useState(null)
  const [userToken, setUserToken] = useState(localStorage.getItem('auth_token') || null)
  const [userRole, setUserRole] = useState(localStorage.getItem('user_role') || null)

  const getEmailFromToken = (token) => {
    if (!token) return null
    try {
      const base64Url = token.split('.')[1]
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
      const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''))
      return JSON.parse(jsonPayload).email
    } catch (e) {
      return null
    }
  }

  const userEmail = getEmailFromToken(userToken)
  const isAdmin = userRole === 'admin'

  const navigateTo = (view, callId = null) => {
    setSelectedCallId(callId)
    setCurrentView(view)
  }

  const [accessDenied, setAccessDenied] = useState(null)
  const [requestingAccess, setRequestingAccess] = useState(false)
  const [requestSent, setRequestSent] = useState(false)

  const handleLogin = async (provider) => {
    try {
      const result = await signInWithPopup(auth, provider)
      const token = await result.user.getIdToken()
      
      const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-cx-4105010761.us-central1.run.app"
      const res = await fetch(`${API_URL}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      
      if (!res.ok) {
        if (res.status === 403) {
          setAccessDenied(result.user.email)
          return
        }
        throw new Error("Login failed")
      }
      
      const userData = await res.json()
      localStorage.setItem('auth_token', token)
      localStorage.setItem('user_role', userData.role)
      setUserToken(token)
      setUserRole(userData.role)
    } catch (err) {
      console.error(err)
      alert("Erro ao validar login. Verifique sua conexão.")
    }
  }

  const handleRequestAccess = async () => {
    setRequestingAccess(true)
    try {
      const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-cx-4105010761.us-central1.run.app"
      const formData = new FormData()
      formData.append('email', accessDenied)
      await fetch(`${API_URL}/api/request-access`, {
        method: 'POST',
        body: formData
      })
      setRequestSent(true)
    } catch (err) {
      alert("Erro ao enviar solicitação.")
    } finally {
      setRequestingAccess(false)
    }
  }

  const handleLogout = () => {
    auth.signOut()
    localStorage.removeItem('auth_token')
    localStorage.removeItem('user_role')
    setUserToken(null)
    setUserRole(null)
    setAccessDenied(null)
    setRequestSent(false)
  }

  useEffect(() => {
    const validateTokenOnMount = async () => {
      if (!userToken) return
      try {
        const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-test-env.coherenceai.com.br"
        const res = await fetch(`${API_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${userToken}` }
        })
        if (!res.ok) {
          handleLogout()
        } else {
          const userData = await res.json()
          setUserRole(userData.role)
          localStorage.setItem('user_role', userData.role)
        }
      } catch (err) {
        console.error("Token verification failed, logging out:", err)
        handleLogout()
      }
    }
    validateTokenOnMount()
  }, [])

  if (accessDenied) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-surface">
        <div className="w-16 h-16 rounded-2xl bg-red-100 flex items-center justify-center text-red-500 mb-6">
          <LogOut size={32} />
        </div>
        <h1 className="text-3xl font-bold mb-2 text-red-600">Acesso Restrito</h1>
        <p className="text-black/60 mb-6 text-center max-w-md">
          O e-mail <strong>{accessDenied}</strong> não possui permissão para acessar esta plataforma.
        </p>
        
        {requestSent ? (
          <div className="bg-green-50 p-6 rounded-xl border border-green-200 text-center max-w-sm">
            <h3 className="text-green-800 font-bold mb-2">Solicitação Enviada!</h3>
            <p className="text-sm text-green-700">O administrador foi notificado. Você receberá um aviso quando o acesso for liberado.</p>
            <button onClick={handleLogout} className="mt-4 text-sm font-semibold text-green-800 hover:underline">Voltar</button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <button 
              onClick={handleRequestAccess}
              disabled={requestingAccess}
              className="bg-primary hover:bg-primary/90 text-white font-medium py-3 px-8 rounded-xl transition-all shadow-sm"
            >
              {requestingAccess ? 'Enviando...' : 'Solicitar Acesso'}
            </button>
            <button onClick={handleLogout} className="text-sm text-black/40 hover:text-black">
              Usar outra conta
            </button>
          </div>
        )}
      </div>
    )
  }

  if (!userToken) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-surface relative overflow-hidden">
        {/* Subtle decorative background blur elements */}
        <div className="absolute top-[-20%] left-[-10%] w-96 h-96 bg-primary/5 rounded-full blur-[120px] pointer-events-none"></div>
        <div className="absolute bottom-[-20%] right-[-10%] w-96 h-96 bg-blue-50/10 rounded-full blur-[120px] pointer-events-none"></div>
        
        <div className="relative z-10 flex flex-col items-center">
          <div className="flex items-center gap-3 mb-8">
            <img 
              src="/logo-top-v2.png" 
              alt="Coherence Logo" 
              className="h-[24px] w-auto object-contain"
              onError={(e) => {
                e.target.src = '/logo-v2.png';
              }}
            />
            <div className="h-6 w-[1px] bg-black/10"></div>
            <div className="flex items-center space-x-1.5 text-xs font-semibold tracking-[0.2em] uppercase whitespace-nowrap">
              <span className="text-[#3b82f6] font-medium">MONITORIA DE</span>
              <span className="text-slate-700 font-bold">CHAMADA</span>
            </div>
          </div>
          
          <div className="glass-panel bg-white/70 backdrop-blur-xl p-10 rounded-3xl border border-black/5 shadow-2xl flex flex-col items-center w-[400px] max-w-[90vw]">
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center text-primary mb-6 border border-primary/5">
              <Headphones size={32} />
            </div>
            <h1 className="text-3xl font-bold mb-3 tracking-tight">Login Universal</h1>
            <p className="text-black/60 mb-8 text-center text-sm leading-relaxed">
              Faça login com a sua plataforma preferida para acessar o painel de Qualidade e Diarização por IA.
            </p>
            <div className="w-full flex flex-col gap-3">
              <button 
                onClick={() => handleLogin(googleProvider)}
                className="w-full flex items-center justify-center gap-3 bg-white border border-black/10 hover:bg-black/5 text-black font-semibold py-3 px-4 rounded-xl transition-all shadow-sm"
              >
                <img src="https://www.svgrepo.com/show/475656/google-color.svg" alt="Google" className="w-5 h-5" />
                Continuar com Google
              </button>
              <button 
                onClick={() => handleLogin(microsoftProvider)}
                className="w-full flex items-center justify-center gap-3 bg-[#2F2F2F] hover:bg-black text-white font-semibold py-3 px-4 rounded-xl transition-all shadow-sm"
              >
                <img src="https://www.svgrepo.com/show/452062/microsoft.svg" alt="Microsoft" className="w-5 h-5" />
                Continuar com Microsoft
              </button>
            </div>
          </div>
          
          <p className="mt-8 text-black/40 text-xs tracking-widest uppercase">
            Powered by Coherence AI
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header Minimalista */}
      <header className="border-b border-black/10 bg-surface/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div 
            className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity"
            onClick={() => navigateTo('dashboard')}
          >
            {/* Logo da Empresa e Subtexto */}
            <div className="flex items-center gap-3">
              <img 
                src="/logo-top-v2.png" 
                alt="Coherence" 
                className="h-[15px] w-auto object-contain"
                onError={(e) => {
                  e.target.style.display = 'none';
                  e.target.nextSibling.style.display = 'flex';
                }}
              />
              {/* Fallback caso a imagem não exista */}
              <div style={{display: 'none'}} className="items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center text-primary">
                  <Headphones size={20} />
                </div>
                <span className="font-bold text-xl tracking-tight">Coherence</span>
              </div>
              
              <div className="h-6 w-[1px] bg-black/10 self-center"></div>
              
              <div className="flex items-center space-x-1 sm:space-x-1.5 text-[0.65rem] sm:text-[0.75rem] font-semibold tracking-[0.15em] sm:tracking-[0.2em] uppercase whitespace-nowrap self-center">
                <span className="text-[#3b82f6] font-medium">MONITORIA DE</span>
                <span className="text-slate-700 font-bold">CHAMADA</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {isAdmin && (
              <button 
                onClick={() => navigateTo(currentView === 'admin' ? 'dashboard' : 'admin')}
                className={`flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-xl border transition-all ${
                  currentView === 'admin' 
                    ? 'border-primary bg-primary/5 text-primary' 
                    : 'border-black/5 hover:bg-black/5 text-black/60 hover:text-black'
                }`}
              >
                <Shield size={16} />
                Painel Admin
              </button>
            )}
            <button 
              onClick={() => navigateTo(currentView === 'settings' ? 'dashboard' : 'settings')}
              className={`flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-xl border transition-all ${
                currentView === 'settings' 
                  ? 'border-primary bg-primary/5 text-primary' 
                  : 'border-black/5 hover:bg-black/5 text-black/60 hover:text-black'
              }`}
            >
              <Settings size={16} />
              Configurações
            </button>
            <button 
              onClick={handleLogout}
              className="flex items-center gap-2 text-sm text-black/60 hover:text-black transition-colors"
            >
              <LogOut size={16} />
              Sair
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-8">
        {currentView === 'dashboard' && (
          <Dashboard onInspectCall={(id) => navigateTo('inspector', id)} userToken={userToken} />
        )}
        {currentView === 'inspector' && selectedCallId && (
          <CallInspector callId={selectedCallId} onBack={() => navigateTo('dashboard')} userToken={userToken} />
        )}
        {currentView === 'admin' && (
          <AdminPanel onBack={() => navigateTo('dashboard')} userToken={userToken} />
        )}
        {currentView === 'settings' && (
          <SettingsPanel />
        )}
      </main>
    </div>
  )
}

export default App
