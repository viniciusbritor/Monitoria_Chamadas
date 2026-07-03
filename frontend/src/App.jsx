import { useState, useEffect } from 'react'
import Dashboard from './components/Dashboard'
import CallInspector from './components/CallInspector'
import SettingsPanel from './components/SettingsPanel'
import { Headphones, LogOut, Settings } from 'lucide-react'
import { auth, signInWithPopup, googleProvider, signInWithEmailAndPassword } from './firebase'

function App() {
  const [currentView, setCurrentView] = useState('dashboard') // 'dashboard' | 'inspector' | 'settings'
  const [selectedCallId, setSelectedCallId] = useState(null)

  // IMPORTANTE: userToken sempre comeca como null para evitar race condition.
  // O token stale do localStorage (de sessoes anteriores) nao pode interferir
  // com o fluxo de ?token= vindo do Portal.
  const [userToken, setUserToken] = useState(null)
  const [userRole, setUserRole] = useState(null)
  const [accessDenied, setAccessDenied] = useState(false)
  const [validating, setValidating] = useState(false)
  const [loginError, setLoginError] = useState(null)
  const [emailLogin, setEmailLogin] = useState('')
  const [passwordLogin, setPasswordLogin] = useState('')

  const API_URL = import.meta.env.VITE_API_URL || "https://monitoria-test-env.coherenceai.com.br"
  const PORTAL_URL = import.meta.env.VITE_PORTAL_URL || "https://coherence-portal-test-c5nbfc5meq-uc.a.run.app"

  // Detecta token vindo do Portal (?token=...). Tem prioridade sobre localStorage.
  // Se nao vier ?token=, usa o do localStorage (usuario voltou em outra aba).
  // CRITICO: este useEffect roda ANTES do validateTokenOnMount. Nao chama handleLogout.
  useEffect(() => {
    console.log('[Monitoria SSO] useEffect[?token=] start')
    const urlParams = new URLSearchParams(window.location.search)
    const tokenFromUrl = urlParams.get('token')
    if (tokenFromUrl) {
      console.log('[Monitoria SSO] ?token= detectado, length=', tokenFromUrl.length)
      localStorage.setItem('auth_token', tokenFromUrl)
      setUserToken(tokenFromUrl)
      // Limpa a URL para nao expor token no historico
      window.history.replaceState({}, document.title, window.location.pathname)
      console.log('[Monitoria SSO] token setado no state + localStorage')
    } else {
      console.log('[Monitoria SSO] sem ?token= na URL, checando localStorage')
      // Sem ?token= na URL: usa o do localStorage (sessao anterior)
      const stored = localStorage.getItem('auth_token')
      if (stored) {
        console.log('[Monitoria SSO] token do localStorage, length=', stored.length)
        setUserToken(stored)
      } else {
        console.log('[Monitoria SSO] sem token em lugar nenhum')
      }
    }
  }, [])

  const navigateTo = (view, callId = null) => {
    setSelectedCallId(callId)
    setCurrentView(view)
  }

  const handleLogout = async () => {
    try {
      await auth.signOut()
    } catch (_) {}
    localStorage.removeItem('auth_token')
    localStorage.removeItem('user_role')
    setUserToken(null)
    setUserRole(null)
    setAccessDenied(false)
    window.location.href = PORTAL_URL + '/dashboard'
  }

  const handleGoogleLogin = async () => {
    setLoginError(null)
    try {
      const result = await signInWithPopup(auth, googleProvider)
      const token = await result.user.getIdToken()
      const resp = await fetch(`${API_URL}/api/auth/portal-sso`, {
        method: 'POST',
        body: new URLSearchParams({ token }),
      })
      if (!resp.ok) {
        if (resp.status === 403) {
          setAccessDenied(true)
          return
        }
        throw new Error(`HTTP ${resp.status}`)
      }
      const data = await resp.json()
      localStorage.setItem('auth_token', data.token)
      localStorage.setItem('user_role', data.role)
      setUserToken(data.token)
      setUserRole(data.role)
    } catch (err) {
      console.error(err)
      setLoginError(err.message || 'Erro no login com Google')
    }
  }

  const handleEmailLogin = async (e) => {
    e.preventDefault()
    setLoginError(null)
    try {
      const result = await signInWithEmailAndPassword(auth, emailLogin, passwordLogin)
      const token = await result.user.getIdToken()
      const resp = await fetch(`${API_URL}/api/auth/portal-sso`, {
        method: 'POST',
        body: new URLSearchParams({ token }),
      })
      if (!resp.ok) {
        if (resp.status === 403) {
          setAccessDenied(true)
          return
        }
        throw new Error(`HTTP ${resp.status}`)
      }
      const data = await resp.json()
      localStorage.setItem('auth_token', data.token)
      localStorage.setItem('user_role', data.role)
      setUserToken(data.token)
      setUserRole(data.role)
    } catch (err) {
      console.error(err)
      const code = err.code || ''
      if (code.includes('invalid-credential') || code.includes('user-not-found') || code.includes('wrong-password')) {
        setLoginError('E-mail ou senha incorretos.')
      } else {
        setLoginError(err.message || 'Erro no login')
      }
    }
  }

  useEffect(() => {
    const validateTokenOnMount = async () => {
      if (!userToken) {
        console.log('[Monitoria SSO] validateTokenOnMount: sem userToken, sai cedo')
        return
      }
      console.log('[Monitoria SSO] validateTokenOnMount start, token length=', userToken.length)
      setValidating(true)
      try {
        const res = await fetch(`${API_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${userToken}` }
        })
        console.log('[Monitoria SSO] /api/auth/me status=', res.status)
        if (!res.ok) {
          if (res.status === 403) {
            setAccessDenied(true)
          }
          // 401/500/etc: NAO chama handleLogout (isso causava o redirect indevido).
          // Apenas limpa o token. O user pode re-tentar.
          if (res.status === 401) {
            console.log('[Monitoria SSO] token invalido (401), limpando')
            localStorage.removeItem('auth_token')
            setUserToken(null)
          }
          // 5xx: nao faz nada (transient)
        } else {
          const userData = await res.json()
          console.log('[Monitoria SSO] /api/auth/me ok, role=', userData.role)
          setUserRole(userData.role)
          localStorage.setItem('user_role', userData.role)
        }
      } catch (err) {
        console.error("[Monitoria SSO] validateTokenOnMount error:", err)
        // Erro de rede: NAO chama handleLogout (que faz redirect)
        // Apenas continua; o user vera a tela de login e pode tentar de novo
      } finally {
        setValidating(false)
      }
    }
    validateTokenOnMount()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userToken])

  if (accessDenied) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-surface">
        <div className="w-16 h-16 rounded-2xl bg-red-100 flex items-center justify-center text-red-500 mb-6">
          <LogOut size={32} />
        </div>
        <h1 className="text-3xl font-bold mb-2 text-red-600">Acesso Restrito</h1>
        <p className="text-black/60 mb-6 text-center max-w-md">
          Você não possui permissão para acessar o módulo Monitoria de Chamadas.
          Solicite acesso ao administrador no Portal Coherence.
        </p>
        <button
          onClick={() => window.location.href = PORTAL_URL + '/dashboard'}
          className="bg-primary hover:bg-primary/90 text-white font-medium py-3 px-8 rounded-xl transition-all shadow-sm"
        >
          Voltar ao Portal
        </button>
      </div>
    )
  }

  if (!userToken) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-surface relative overflow-hidden">
        <div className="absolute top-[-20%] left-[-10%] w-96 h-96 bg-primary/5 rounded-full blur-[120px] pointer-events-none"></div>
        <div className="absolute bottom-[-20%] right-[-10%] w-96 h-96 bg-blue-50/10 rounded-full blur-[120px] pointer-events-none"></div>

        <div className="relative z-10 flex flex-col items-center">
          <div className="flex items-center gap-3 mb-8">
            <img
              src="/logo-top-v2.png"
              alt="Coherence"
              className="h-[24px] w-auto object-contain"
              onError={(e) => { e.target.src = '/logo-v2.png' }}
            />
            <div className="h-6 w-[1px] bg-black/10"></div>
            <div className="flex items-center space-x-1.5 text-xs font-semibold tracking-[0.2em] uppercase whitespace-nowrap">
              <span className="text-[#3b82f6] font-medium">MONITORIA DE</span>
              <span className="text-slate-700 font-bold">CHAMADA</span>
            </div>
          </div>

          <div className="glass-panel bg-white/70 backdrop-blur-xl p-8 rounded-3xl border border-black/5 shadow-2xl flex flex-col items-center w-[400px] max-w-[90vw]">
            <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center text-primary mb-5 border border-primary/5">
              <Headphones size={28} />
            </div>
            <h1 className="text-2xl font-bold mb-2 tracking-tight">Login</h1>
            <p className="text-black/60 mb-6 text-center text-sm leading-relaxed">
              Acesse com sua conta do Portal Coherence.
            </p>

            {loginError && (
              <div className="w-full bg-red-50 border border-red-200 text-red-700 text-xs p-2 rounded-lg mb-4 text-center">
                {loginError}
              </div>
            )}

            <form onSubmit={handleEmailLogin} className="w-full flex flex-col gap-2 mb-4">
              <input
                type="email"
                placeholder="Seu e-mail"
                value={emailLogin}
                onChange={(e) => setEmailLogin(e.target.value)}
                required
                className="w-full bg-white/80 border border-black/10 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              />
              <input
                type="password"
                placeholder="Sua senha"
                value={passwordLogin}
                onChange={(e) => setPasswordLogin(e.target.value)}
                required
                className="w-full bg-white/80 border border-black/10 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              />
              <button
                type="submit"
                className="w-full bg-primary hover:bg-primary/90 text-white font-semibold py-2.5 rounded-lg transition-all"
              >
                Entrar
              </button>
            </form>

            <div className="flex items-center gap-3 w-full my-1 opacity-30">
              <div className="h-[1px] flex-1 bg-black" />
              <span className="text-[10px] font-semibold uppercase tracking-widest text-black">ou</span>
              <div className="h-[1px] flex-1 bg-black" />
            </div>

            <button
              onClick={handleGoogleLogin}
              className="w-full flex items-center justify-center gap-3 border border-black/10 py-2.5 px-4 rounded-lg bg-white hover:bg-black/5 transition-all shadow-sm font-semibold mt-2"
            >
              <img src="https://www.svgrepo.com/show/475656/google-color.svg" alt="Google" className="w-5 h-5" />
              Continuar com Google
            </button>

            <button
              onClick={() => window.location.href = PORTAL_URL + '/dashboard'}
              className="mt-5 text-xs text-black/40 hover:text-black/70"
            >
              Voltar ao Portal
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (validating) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface">
        <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-black/10 bg-surface/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div 
            className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity"
            onClick={() => navigateTo('dashboard')}
          >
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

      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-8">
        {currentView === 'dashboard' && (
          <Dashboard onInspectCall={(id) => navigateTo('inspector', id)} userToken={userToken} />
        )}
        {currentView === 'inspector' && selectedCallId && (
          <CallInspector callId={selectedCallId} onBack={() => navigateTo('dashboard')} userToken={userToken} />
        )}
        {currentView === 'settings' && (
          <SettingsPanel />
        )}
      </main>
    </div>
  )
}

export default App
