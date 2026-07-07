# Conexão do Módulo Monitoria (Portal ↔ Módulo)

> ⚠️ **AVISO:** Esta é uma **cópia de referência** para o módulo Monitoria. A **fonte canônica** está em `Coherence_Portal/docs/conexao_modulo.md` (e `.json`). O Portal consulta o spec para renderizar o módulo corretamente.
>
> Se houver divergência, **Portal ganha**. Atualize o Portal primeiro, depois sincronize este arquivo.

---

## Resumo executivo

**module_id:** `monitoria-chamadas` (constante imutável)

**Variante test ativa:**
- URL: `https://monitoria-test-env-894828119087.us-central1.run.app`
- URL alias (deprecated): `https://monitoria-test-env-c5nbfc5meq-uc.a.run.app`
- Cloud Run: `monitoria-test-env`
- Branch: `test`
- Build: `cloudbuild-test.yaml`

**O que o Portal faz quando user clica no card:**
```js
window.open(`${m.url}?token=${firebase_id_token}`, '_blank')
```

**O que este módulo faz ao receber a URL com token:**
1. `POST /api/auth/portal-sso` (no módulo) com o token
2. Valida via Firebase Admin SDK
3. Cria sessão local (JWT em `localStorage`)
4. Para cada request autenticado: chama Portal `/api/me/permissions?email=X` e `/api/me/role?email=X`
5. Em negação de acesso: `POST /api/admin/audit-logs/log-access-denied`

---

## APIs que o Portal PROVE (que este módulo CONSOME)

| Método | Path | Quando |
|---|---|---|
| `GET` | `/api/me/permissions?email=X` | Toda request autenticada (TTL 300s cache) |
| `GET` | `/api/me/role?email=X` | Toda request autenticada (TTL 300s cache) |
| `POST` | `/api/admin/audit-logs/log-access-denied` | Quando módulo nega acesso (fire-and-forget) |

**Implementação:** `core/portal_auth.py` e `core/portal_audit.py`

---

## Identidade própria (módulo conhece a si mesmo)

```python
# core/models.py (no Portal) ou backend/models.py (no módulo)
MONITORIA_MODULE_ID = "monitoria-chamadas"  # constante
```

---

## Schema Firestore esperado em `modules/monitoria-chamadas`

```json
{
  "module_id": "monitoria-chamadas",
  "name": "Monitoria de Chamadas",
  "url": "https://monitoria-test-env-894828119087.us-central1.run.app"
}
```

**Source of truth:** Firestore (criado via Portal admin API ou console, NUNCA via seed deste módulo).

---

## Capability check (este módulo)

- ✅ Audio formats: MP3, WAV, MPEG
- ✅ Transcrição: faster-whisper base (PT-BR)
- ✅ QA: MiniMax M3
- ✅ Worker: `monitoria-whisper-worker` (Pub/Sub consumer)

---

## Spec canônico completo

Para o schema JSON validável e a documentação humana detalhada (13 seções), veja:
- **Portal**: `C:\Users\vinic\workspace_antigravity\Coherence_Portal\docs\conexao_modulo.md`
- **JSON**: `C:\Users\vinic\workspace_antigravity\Coherence_Portal\docs\conexao_modulo.json`

---

**Última sincronização:** 2026-07-07
**Mantido por:** viniciusbritor@gmail.com
## Mudancas em 03/07/2026 (sincronizado com Portal)

Apos a Fase 8 (commit `ee292b5` do Portal), o contrato foi **consolidado**:

- ANTES (Fase 4-7): 3 endpoints separados
  - `GET /api/me/permissions?email=X`
  - `GET /api/me/role?email=X`
  - `POST /api/admin/audit-logs/log-access-denied`

- AGORA (Fase 8): **1 endpoint canonico**
  - `GET /api/auth/me?module_id=<id>`
  - Header: `Authorization: Bearer <firebase_id_token>`
  - Resposta: `{email, is_super_admin, client_id, role, modules{}}`
  - 403 + audit log automatico se `?module_id=X` e user sem permissao

Endpoints legados ainda funcionam mas sao deprecated.
