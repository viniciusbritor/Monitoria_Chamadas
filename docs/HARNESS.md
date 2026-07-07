# 🚀 Harness do Projeto

> **Objetivo Principal:** Sistema de "Monitoria de Chamadas" baseado em IA. Transcreve áudios de atendimento ao cliente usando Whisper (local ou Cloud Run) e os avalia contra critérios de qualidade utilizando Gemini (Google), fornecendo notas (QA Score) e feedback através de um Dashboard web interativo.

## 🔐 Acesso ao Módulo — SEMPRE via Portal Coherence

> **IMPORTANTE:** A URL do Cloud Run `https://monitoria-test-env-c5nbfc5meq-uc.a.run.app/` **NÃO é endpoint público para usuários finais**. É detalhe de implementação interno do ecossistema Coherence.

**Único fluxo válido:**
1. Usuário acessa `https://coherence-portal-test-c5nbfc5meq-uc.a.run.app/`
2. Faz login (Firebase SSO via Google ou email/senha)
3. No Dashboard do Portal, clica no card **"Monitoria de Chamadas"**
4. O Portal abre o módulo em nova aba: `window.open(${module.url}?token=${firebase_id_token}, '_blank')`
5. O módulo valida o token via `GET /api/auth/me` no Portal e renderiza o dashboard autenticado

**Acesso direto (colar a URL no navegador):**
- Exibe a página "Acesso via Portal Coherence" com botão de redirect.
- Backend loga como `[Security] direct-access attempt from <IP>` para auditoria.

**Para testes/desenvolvimento local:**
- Use `frontend/.env.example` → `frontend/.env.local` apontando para `VITE_API_URL=http://127.0.0.1:8001`.
- **Não compartilhe** a URL pública do Cloud Run como ponto de entrada para demos ou testes com usuários reais.

## 🧪 Ambiente de Teste vs Produção
- **REGRA ESTABELECIDA:** A primeira implementação de qualquer nova funcionalidade ou alteração **SEMPRE** deve ser feita no ambiente de Teste/Homologação (`Monitoria_Chamadas_Teste`). Nenhuma alteração deve ser feita diretamente no ambiente de produção.
- Após a implementação no ambiente de teste, o usuário avaliará e decidirá se as alterações devem ser "viradas" para Produção.

## 📂 Estrutura de Diretórios
- `/core`: Lógicas isoladas de IA (`transcriber.py`, `evaluator.py`).
- `/frontend`: Aplicação React/Vite isolada (dist build é servido estaticamente no backend FastAPI).
- `api.py`: Roteador principal FastAPI e BackgroundTasks.
- `Dockerfile`: Arquivo responsável pela construção da infraestrutura no GCP (Cloud Run).
- `/docs`: Documentação técnica essencial.

## 🔑 Autenticação e Segredos
- O projeto consome segredos via env vars injetadas no deploy (`gcloud run services update --update-env-vars`). A variável crítica é `MINIMAX_API_KEY` (LLM MiniMax M3 para extração de QA), extraída de `secrets_manager.py` (banco cofre local) durante o deploy. **Nunca commitada em código ou YAML.** Ver `docs/DIARIO_BORDO.md` 28/06/2026 (bug `login fail: Please carry the API secret key` no deploy).

## 🤝 SSO com Portal Coherence (Fase 8 — 03/07/2026)

O Monitoria **consome o endpoint canônico de SSO** do Portal para validar sessão + permissões:

```http
GET {PORTAL_API_URL}/api/auth/me[?module_id=<id>]
Authorization: Bearer <firebase_id_token>
```

- **200** → payload `{email, is_super_admin, client_id, role, modules{}}`. User tem permissão.
- **403** → Portal gravou `ACCESS_DENIED` automaticamente. User sem permissão.
- **401/503** → falha transitória.

**Helpers em `core/portal_auth.py`:**
- `is_authorized_for_module(email, module_id, firebase_id_token) → bool`
- `get_user_role_and_admin(email, firebase_id_token) → dict`
- `require_admin_user(authorization: str = Header(None)) → dict` (FastAPI dependency)

**Cache:** TTL 300s in-memory, chave `(token_hash, module_id)`. Isolamento por usuário (token).

**Uso típico em `api.py`:**
```python
def get_current_user(authorization: str = Header(None)):
    token = authorization.split("Bearer ", 1)[1]
    decoded = fb_auth.verify_id_token(token)  # valida localmente
    email = decoded["email"]
    if not is_authorized_for_module(email, MODULE_ID, token):
        raise HTTPException(403, f"Acesso negado: {email} sem permissao para '{MODULE_ID}'")
    role_info = get_user_role_and_admin(email, token)
    return decoded
```

> **ATENÇÃO:** desde a Fase 8, NÃO chamar `log_access_denied()` manualmente após `is_authorized_for_module()` retornar False. O Portal grava `ACCESS_DENIED` automaticamente no 403 — chamada extra é ruído. (Audit log removido de `api.py` linhas 152 e 181 na commit `a8bc446`.)

**Procedimento de rotação de URL do Portal:** ver `docs/HARNESS.md` do Portal (seção "Rotação de URL de Módulo"). Resumo: atualizar `PORTAL_API_URL` no `cloudbuild-test.yaml` do Monitoria → commit + push → redeploy. Cache TTL 300s garante que a próxima chamada HTTP pega a URL nova.

## 🏗️ Build do Frontend (Vite) — Variáveis de Ambiente
- **REGRA CRÍTICA:** A variável `VITE_API_URL` **DEVE** ser injetada via Cloud Build substitutions (`cloudbuild-test.yaml` ou `cloudbuild.yaml`) ANTES do `npm run build`. Nunca deixar `VITE_API_URL` cair no fallback hard-coded.
- **NÃO criar `frontend/.env.local`** — esse arquivo é ignorado pelo git mas seu conteúdo é embutido no bundle JS compilado, podendo causar bugs sutis de URL (vide DIARIO_BORDO 03/07/2026).
- Para desenvolvimento local, copie `frontend/.env.example` → `frontend/.env.local` e ajuste a `VITE_API_URL` para `http://127.0.0.1:8001`.
- **Cache-bust:** o `cloudbuild-test.yaml` cria o arquivo `frontend/.cache-bust` antes do build para forçar o navegador a recarregar o `index.html` (que tem `Cache-Control: no-store` no backend).

## Histórico de Erros e Resoluções
- **Erro de "Erro no upload" no ambiente de teste (03/07/2026):** O bundle JS em `frontend/dist/` foi compilado com `VITE_API_URL=http://127.0.0.1:8001` (dev local), fazendo o navegador do usuário tentar POST para localhost. Bug adicional: 3 arquivos `.jsx` tinham fallback apontando para a URL de produção. Corrigido rebuildando o frontend com a URL correta e alinhando os fallbacks.
- **Erro de Falhou na Interface:** Ao enviar áudios, a interface do usuário exibia o status Falhou após um longo tempo aguardando. Isso ocorreu porque o processo do Whisper no Cloud Run consome tempo substancial de CPU e a interface assumia um timeout ou um erro prematuro, apesar de o servidor continuar processando e salvar os resultados corretamente no **Firestore** (collection `chamadas`). Foi mitigado ajustando a alocação de threads no Whisper e documentando a necessidade de paciência do usuário devido ao uso de CPU. (Pré-06/07/2026 a persistência era em SQLite GCS FUSE; migrada para Firestore no Plano A++.)

## Visual Identity
All UI changes must strictly follow [UI_GUIDELINES.md](UI_GUIDELINES.md) ensuring the Coherence visual identity guidelines (Clean Light Glassmorphism).