import { useState, useEffect } from 'react'
import Dashboard from './components/Dashboard'
import CallInspector from './components/CallInspector'
import SettingsPanel from './components/SettingsPanel'
import QueueManager from './components/QueueManager'
import { Headphones, LogOut, Settings, Inbox } from 'lucide-react'
import { auth } from './firebase'

// NEW (05/07/2026): loader brandado compartilhado.
// Usado durante o bootstrap (validacao do ?token=) e durante a validacao inicial.
// Da' uma transicao visual suave do Portal -> Monitoria (sem flash de tela em branco).
function BrandedLoader({ message = 'Conectando ao Portal Coherence...' }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-surface transition-page">
      <div className="flex flex-col items-center gap-6 max-w-md px-6">
        <div className="flex items-center gap-3 animate-logo-in">
          <img
            src="/logo-top-v2.png"
            alt="Coherence"
            className="h-[28px] w-auto object-contain"
            onError={(e) => { e.target.src = '/logo-v2.png' }}
          />
          <div className="h-7 w-[1px] bg-black/10"></div>
          <div className="flex items-center space-x-1.5 text-xs font-semibold tracking-[0.2em] uppercase whitespace-nowrap">
            <span className="text-[#3b82f6] font-medium">MONITORIA DE</span>
            <span className="text-slate-700 font-bold">CHAMADA</span>
          </div>
        </div>

        <div className="flex flex-col items-center gap-3 animate-fadeInUp">
          <div className="w-10 h-10 rounded-2xl bg-primary/10 flex items-center justify-center text-primary">
            <Headphones size={20} />
          </div>
          <p className="text-sm text-black/60 animate-pulse-soft">{message}</p>
          <div className="w-48 h-[2px] bg-black/5 rounded-full overflow-hidden mt-1">
            <div className="h-full w-1/3 bg-primary rounded-full animate-progress"></div>
          </div>
        </div>
      </div>
    </div>
  )
}

function App() {
  const [currentView, setCurrentView] = useState('dashboard') // 'dashboard' | 'inspector' | 'settings' | 'queue'
  const [selectedCallId, setSelectedCallId] = useState(null)

  // IMPORTANTE: userToken sempre comeca como null para evitar race condition.
  // O token stale do localStorage (de sessoes anteriores) nao pode interferir
  // com o fluxo de ?token= vindo do Portal.
  const [userToken, setUserToken] = useState(null)
  const [userRole, setUserRole] = useState(null)
  const [accessDenied, setAccessDenied] = useState(false)
  const [validating, setValidating] = useState(false)
  // NEW (05/07/2026): modulo e' acessivel APENAS via Portal Coherence (?token= na URL).
  // Nao ha mais Login proprio: acesso direto redireciona para o Portal.
  const [bootstrapping, setBootstrapping] = useState(true)

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
    // NEW (Sprint 2 - 03/07/2026): encerra bootstrap. Apos isso o componente pode decidir
    // entre mostrar login, validating ou dashboard, conforme o userToken atual.
    setBootstrapping(false)
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

  // NEW (05/07/2026): loader brandado compartilhado (definido em escopo de modulo acima).

  if (bootstrapping) {
    return <BrandedLoader message="Conectando ao Portal Coherence..." />
  }

  if (accessDenied) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-surface transition-page">
        <div className="flex flex-col items-center gap-5 animate-fadeInUp">
          <div className="w-16 h-16 rounded-2xl bg-red-100 flex items-center justify-center text-red-500">
            <LogOut size={32} />
          </div>
          <h1 className="text-3xl font-bold text-red-600">Acesso Restrito</h1>
          <p className="text-black/60 text-center max-w-md leading-relaxed">
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
      </div>
    )
  }

  if (!userToken) {
    // Acesso direto (sem ?token= vindo do Portal): modulo NAO expoe Login proprio.
    // Usuario deve passar pelo Portal Coherence.
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-surface px-4 transition-page">
        <div className="flex flex-col items-center gap-5 max-w-md animate-fadeInUp">
          <div className="flex items-center gap-3 mb-1">
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

          <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center text-primary">
            <Headphones size={32} />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">Acesso via Portal Coherence</h1>
          <p className="text-black/60 text-center text-sm leading-relaxed">
            A Monitoria de Chamadas é um módulo do ecossistema Coherence e pode ser acessada
            exclusivamente pelo Portal. Faça login no Portal e abra o card "Monitoria de Chamadas".
          </p>
          <button
            onClick={() => window.location.href = PORTAL_URL + '/dashboard'}
            className="bg-primary hover:bg-primary/90 text-white font-medium py-3 px-8 rounded-xl transition-all shadow-sm mt-2"
          >
            Ir para o Portal Coherence
          </button>
        </div>
      </div>
    )
  }

  if (validating) {
    return <BrandedLoader message="Validando sessão no Portal Coherence..." />
  }

  return (
    <div className="min-h-screen flex flex-col transition-page">
      <header className="border-b border-black/10 bg-surface/80 backdrop-blur sticky top-0 z-50 transition-content">
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
            {userRole === 'admin' && (
              <button
                onClick={() => navigateTo(currentView === 'queue' ? 'dashboard' : 'queue')}
                className={`flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-xl border transition-all ${
                  currentView === 'queue'
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-black/5 hover:bg-black/5 text-black/60 hover:text-black'
                }`}
              >
                <Inbox size={16} />
                Fila
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

      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-8 transition-content">
        <div key={currentView + (selectedCallId || '')} className="transition-content">
          {currentView === 'dashboard' && (
            <Dashboard onInspectCall={(id) => navigateTo('inspector', id)} userToken={userToken} />
          )}
          {currentView === 'inspector' && selectedCallId && (
            <CallInspector callId={selectedCallId} onBack={() => navigateTo('dashboard')} userToken={userToken} />
          )}
          {currentView === 'settings' && (
            <SettingsPanel />
          )}
          {currentView === 'queue' && (
            <QueueManager userToken={userToken} onBack={() => navigateTo('dashboard')} />
          )}
        </div>
      </main>
    </div>
  )
}

export default App
