# 🔌 Integração do Módulo Monitoria de Chamadas com o Portal

> **Status**: Padrão vigente desde 08/07/2026.
> **Padrão canônico**: `OmniChannel/docs/MODULE_INTEGRATION.md`.
> **Visão do Portal**: `Coherence_Portal/docs/MODULE_INTEGRATION.md`.

## 🎯 Quem é este módulo

**Monitoria de Chamadas** (`module_id: monitoria-chamadas`) é um módulo do ecossistema OmniChannel. Processa áudios de atendimento via Whisper + LLM para gerar nota QA, NPS e motivos.

## 📋 Dados de Cadastro (chamar após deploy)

| Campo | Valor (test) |
|---|---|
| `module_id` | `monitoria-chamadas` |
| `name` | `Monitoria de Chamadas` |
| `url` | `https://monitoria-test-env-c5nbfc5meq-uc.a.run.app` |
| `revision` | `<última revision do Cloud Run>` (atualizado a cada deploy) |
| `description` | `Transcricao e avaliacao QA de chamadas usando Whisper + LLM` |
| `icon` | `Headphones` (lucide-react) |

## 🚀 Como Registrar/Atualizar este Módulo no Portal

### Opção 1 — Via curl (manual, após deploy)

```bash
# 1. Obter URL e revision atual do Cloud Run
SERVICE_URL=$(gcloud run services describe monitoria-test-env \
  --region=us-central1 --format="value(status.url)")
REVISION=$(gcloud run services describe monitoria-test-env \
  --region=us-central1 --format="value(status.latestReadyRevisionName)")

# 2. Obter Firebase ID Token do super-admin
# (rodar fora do Cloud Build — em workstation local)
TOKEN=$(gcloud auth print-identity-token \
  --audiences="https://coherence-portal-test-c5nbfc5meq-uc.a.run.app")

# 3. Chamar API admin do Portal
curl -s -X POST \
  "https://coherence-portal-test-c5nbfc5meq-uc.a.run.app/api/admin/modules/monitoria-chamadas" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Monitoria de Chamadas\",
    \"url\": \"$SERVICE_URL\",
    \"revision\": \"$REVISION\",
    \"description\": \"Transcricao e avaliacao QA de chamadas\",
    \"icon\": \"Headphones\"
  }"
```

### Opção 2 — Via Cloud Build (automatizado, recomendado)

Adicionar **step final** em `cloudbuild-test.yaml` e `cloudbuild-worker.yaml`:

```yaml
# Step N (apos deploy do test-env): notifica Portal
- name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
  entrypoint: bash
  args:
    - '-c'
    - |
      SERVICE_URL=$(gcloud run services describe monitoria-test-env \
        --region=us-central1 --format="value(status.url)")
      REVISION=$(gcloud run services describe monitoria-test-env \
        --region=us-central1 --format="value(status.latestReadyRevisionName)")
      PORTAL_URL="https://coherence-portal-test-c5nbfc5meq-uc.a.run.app"
      TOKEN=$(curl -s -H "Metadata-Flavor: Google" \
        "http://metadata/computeMetadata/v1/instance/service-accounts/default/identity?audience=$PORTAL_URL")
      curl -s -X POST \
        "$PORTAL_URL/api/admin/modules/monitoria-chamadas" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"Monitoria de Chamadas\",\"url\":\"$SERVICE_URL\",\"revision\":\"$REVISION\",\"description\":\"Transcricao e avaliacao QA de chamadas\",\"icon\":\"Headphones\"}"
```

**Pré-requisito**: o Cloud Build SA precisa ser super-admin no Portal (adicionado em `SUPER_ADMIN_EMAILS` env var do Portal Cloud Run).

## 🔐 Permissões

- `monitoria-chamadas` é acessível para usuários que têm `user_permissions/{email}_monitoria-chamadas.is_active == true`
- Portal retorna 403 + audit log `ACCESS_DENIED` se user tenta acessar sem permissão
- Card aparece no Dashboard se user tem permissão **OU** é super-admin

## 🔄 Fluxo End-to-End

```
1. Dev edita codigo + atualiza docs/MODULE_INTEGRATION.md (este arquivo) se necessario
2. git commit + push na branch test
3. Cloud Build dispara cloudbuild-test.yaml:
   a. pytest
   b. npm build (frontend)
   c. docker build + push
   d. gcloud run deploy monitoria-test-env (nova revision)
   e. (NOVO) curl POST /api/admin/modules/monitoria-chamadas
4. Portal atualiza Firestore `modules/monitoria-chamadas.url` = nova URL
5. Frontend Portal recarrega cards na proxima sessao
6. User clica no card "Monitoria de Chamadas" → abre URL nova
```

## 📊 Contratos que este módulo CONSOME do Portal

- `GET /api/auth/me?module_id=monitoria-chamadas` — valida sessão + permissão
- `GET /api/modules` — lista módulos (não usado direto, mas o Portal consulta internamente)
- `POST /api/admin/modules/monitoria-chamadas` — **este módulo EXPÕE** info para o Portal (novo)

## 📊 Contratos que este módulo EXPÕE para o Portal

- `GET /` — UI do módulo (com `?token=...`)
- `GET /api/auth/me` — usado internamente
- `GET /api/calls` — lista chamadas
- `POST /api/upload` — upload single
- `POST /api/upload-batch` — upload em batch (max 50 arquivos, max 20MB cada)
- `POST /api/internal/calls/{id}/status` — worker callback (legado, ver `LEGACY_CALLBACK`)

## ⚠️ Histórico deste módulo

| Data | Mudança |
|---|---|
| 06/07/2026 | Migração para Firestore (Plano A++) |
| 07/07/2026 | Multi-provider LLM (DeepSeek + NVIDIA + MiniMax) |
| 07/07/2026 | Plano Ultra-Econômico aplicado (~$110/mês, 600 calls/dia) |
| 08/07/2026 | Worker escreve direto no Firestore (sem callback OIDC) |
| 08/07/2026 | LLM batch (1 chamada = diarize + evaluate) |
| 08/07/2026 | Batch upload (50 arquivos/req) |
| 08/07/2026 | Adoção do padrão de integração (este documento) |

## 📚 Referências

- `OmniChannel/docs/MODULE_INTEGRATION.md` — padrão canônico
- `Coherence_Portal/docs/MODULE_INTEGRATION.md` — visão do Portal
- `docs/HARNESS.md` — como rodar este módulo
- `docs/ARQUITETURA.md` — arquitetura interna
- `docs/GUARDRAILS.md` — regras inegociáveis