# 🗺️ Backlog Agêntico: Queue Manager Module (Monitoria)

> **Objetivo:** módulo admin para visualizar e gerenciar mensagens pendentes na subscription Pub/Sub `monitoria-whisper-jobs-worker`. Eliminar o problema de "fila invisível" quando o worker crasha.

---

## 🏗️ Sprint 1: Fundação (RBAC + Helpers Pub/Sub)

- [ ] **Task 1.1 — Helper `core/pubsub_admin.py`**: encapsular `pubsub_v1.SubscriberClient` com métodos `list_pending(limit, page_token)`, `acknowledge(message_id, ack_id)`, `retry(message_data, attributes)`, `get_stats()`. Usa `subscriber.pull(return_immediately=True, max_messages=50)` + ack dentro de 5s para não consumir de fato.
- [ ] **Task 1.2 — Helper de auth admin**: decorator `require_admin` em `core/portal_auth.py` que valida `user["is_super_admin"]` via cookie/JWT já existente (mesmo padrão do `AdminPanel`).
- [ ] **Task 1.3 — Convenção de nomes**: criar entry `monitoria-queue-manager` no Firestore (`user_permissions/`) para RBAC, vinculado ao `super_admin` por padrão.

## 🤖 Sprint 2: Backend — Endpoints `/api/queue/*`

- [ ] **Task 2.1 — `GET /api/queue/stats`**: retorna `{ message_count, oldest_unacked_seconds, ack_deadline_seconds, worker_healthy }`. `worker_healthy` = GET `/healthz` interno do worker via Service URL.
- [ ] **Task 2.2 — `GET /api/queue/messages?limit=50&page_token=...`**: lista mensagens pendentes com `{ message_id, ack_id, publish_time, attributes, payload_preview (256 chars JSON) }`. Paginação via `subscription.pull` response.
- [ ] **Task 2.3 — `POST /api/queue/messages/{message_id}/ack`**: acknowledge imediato (descarta). Loga em `audit_logs` no Portal.
- [ ] **Task 2.4 — `POST /api/queue/messages/{message_id}/retry`**: republica no tópico `monitoria-whisper-jobs` como nova mensagem (novo `message_id`, mesmo payload).
- [ ] **Task 2.5 — `POST /api/queue/purge`**: ack em massa de TODAS pendentes (requer `confirm=true` no body). Loga o evento.

## ⚙️ Sprint 3: Frontend — `QueueManager.jsx`

- [ ] **Task 3.1 — Componente base**: rota `currentView === 'queue'`. Reusa ShortPolling (5s) como `Dashboard.jsx`.
- [ ] **Task 3.2 — Cabeçalho de saúde**: badge verde/amarelo/vermelho com `message_count` e idade do oldest. Botão "Atualizar" manual.
- [ ] **Task 3.3 — Tabela de mensagens**: colunas `[ID | Publicada em | Filename | Idade | Ações]`. Ações inline: `Inspecionar`, `Descartar`, `Reprocessar`. Modal de inspeção com payload JSON completo.
- [ ] **Task 3.4 — Botão "Limpar tudo"** com confirmação dupla (digitar `CONFIRMAR`).
- [ ] **Task 3.5 — Botão de entrada no app.jsx**: novo item no cabeçalho `navigateTo('queue')` visível só se `user.is_super_admin === true`.
- [ ] **Task 3.6 — Identidade visual**: respeita `UI_GUIDELINES.md` (Clean Light Glassmorphism, mesmos componentes de card).

## 🚀 Sprint 4: Deploy + Validação

- [ ] **Task 4.1 — Build**: `gcloud builds submit --config=cloudbuild-test.yaml --substitutions=COMMIT_SHA=<sha>` (~5min).
- [ ] **Task 4.2 — Smoke test E2E**: subir worker morto (forçar crash via `gcloud run services update --max-instances=0`), enviar 3 áudios, abrir `/queue`, validar que aparecem como pendentes, validar `Reprocessar` funciona após worker voltar.
- [ ] **Task 4.3 — Auditoria**: cada ação admin (`ack`, `retry`, `purge`) grava em `audit_logs` no Portal via `core/portal_audit.py`.
- [ ] **Task 4.4 — Doc**: entrada em `DIARIO_BORDO.md` descrevendo o módulo, decisão arquitetural (pull+ack vs snapshot), e lições aprendidas.

---

## 📊 Métricas de Sucesso

- 100% das mensagens pendentes visíveis no painel
- Latência de listagem < 1s (subscription tipicamente tem < 100 msgs)
- Zero mensagens órfãs invisíveis (verificado via `subscription.pull` retorna 0)

## 🔐 Permissões

- Visible: `is_super_admin=True` OU `user_permissions["monitoria-queue-manager"]=true`
- Leitura do audit log: idem ao AdminPanel atual
