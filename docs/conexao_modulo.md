# Conexao do Modulo Monitoria (Portal <-> Modulo)

> AVISO: Esta e' uma copia de referencia para o modulo Monitoria.
> A fonte canonica esta em `Coherence_Portal/docs/conexao_modulo.md` (e .json).
> O Portal consulta este spec para renderizar o modulo corretamente.
> Se houver divergencia, Portal ganha. Atualize o Portal primeiro, depois sincronize este arquivo.

---

## Resumo executivo

**module_id:** `monitoria-chamadas` (constante imutavel)

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

**O que este modulo faz ao receber a URL com token:**
1. `POST /api/auth/portal-sso` (no modulo) com o token
2. Valida via Firebase Admin SDK
3. Cria sessao local (JWT em `localStorage`)
4. Para cada request autenticado: chama Portal `/api/auth/me?module_id=...`
5. Em negacao de acesso: retorna 403 + mostra tela "Acesso Restrito"

---

## APIs que o Portal PROVE (que este modulo CONSOME)

| Metodo | Path | Quando |
|---|---|---|
| `GET` | `/api/auth/me?module_id=monitoria-chamadas` | Toda request autenticada (validacao de sessao) |

**Implementacao:** `core/portal_auth.py`

Resposta 200 OK:
```json
{
  "email": "user@example.com",
  "is_super_admin": true,
  "client_id": "...",
  "role": "admin",
  "modules": {
    "monitoria-chamadas": {
      "is_active": true,
      "role": "admin",
      "client_id": "..."
    }
  }
}
```

Resposta 403 Forbidden: user nao tem permissao no modulo. Audit log automatico.

---

## Identidade propria (modulo conhece a si mesmo)

```python
# backend/models.py ou core/portal_auth.py
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

**Source of truth:** Firestore (criado via Portal admin API ou console, NUNCA via seed deste modulo).

---

## Objetivo Principal do Modulo (Negocio)

1. Upload de chamada (audio file)
2. Transcricao audio -> texto
3. Separar audio atendente e cliente
4. Avaliar nota QA do atendente e nota NPS do cliente
5. Categorizar motivos principais da chamada

---

## Capability check (este modulo)

- Audio formats: MP3, WAV, MPEG
- Transcricao: faster-whisper base (PT-BR)
- QA: MiniMax M3
- Worker: `monitoria-whisper-worker` (Pub/Sub consumer)

---

## Spec canonico completo

Para o schema JSON validavel e a documentacao humana detalhada, veja:
- **Portal**: `C:\Users\vinic\workspace_antigravity\Coherence_Portal\docs\conexao_modulo.md`
- **JSON**: `C:\Users\vinic\workspace_antigravity\Coherence_Portal\docs\conexao_modulo.json`

---

**Ultima sincronizacao:** 2026-07-07
**Mantido por:** viniciusbritor@gmail.com
