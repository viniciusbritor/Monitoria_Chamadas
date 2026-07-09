# Política de Privacidade — Monitoria de Chamadas

> **Versão**: 1.0 — 08/07/2026
> **LGPD Art. 9**: "O titular tem direito de obter informação clara e adequada sobre os seus dados".
> **Canônica**: `OmniChannel/docs/LGPD_COMPLIANCE.md` (harness global).

## 1. Quem somos

**Controlador**: Coherence AI
**Encarregado de Dados (DPO)**: Vinicius Brito (viniciusbritor@gmail.com)
**Módulo**: Monitoria de Chamadas (parte do ecossistema OmniChannel/Coherence)

## 2. Quais dados coletamos

| Categoria | Dados específicos | Finalidade |
|---|---|---|
| **Áudio** | Gravações de chamadas (.mp3/.wav) | Transcrição + avaliação de qualidade |
| **Transcrição** | Texto transcrito (com PII mascarada antes de LLM) | Avaliação de qualidade |
| **Avaliação IA** | Notas QA, NPS, sentimentos, motivos | Relatórios de qualidade |
| **Metadados** | `filename`, `user_id`, `uploaded_at`, `audio_duration_sec` | Operação do serviço |
| **Audit logs** | Ações do user (download, exclusão) | LGPD Art. 37 |

## 3. PII Mascarada

Antes de enviar para LLM (DeepSeek, NVIDIA, MiniMax), o `core/masker.py` substitui:

- **CPF**: `123.456.789-00` → `[CPF]`
- **RG**: `12.345.678-X` → `[RG]`
- **Telefone**: `(11) 98765-4321` → `[PHONE]`
- **Email**: `joao@example.com` → `[EMAIL]`
- **Cartão**: `1234 5678 9012 3456` → `[CARD]`

**Garantia**: transcrição NUNCA contém PII quando enviada para LLM (LGPD Art. 12).

## 4. Por quanto tempo mantemos

| Tipo | Retenção | Mecanismo |
|---|---|---|
| Gravações de áudio (GCS) | 90 dias | Lifecycle policy |
| Transcrições (Firestore `chamadas/`) | 365 dias | TTL field `created_at` |
| Avaliação IA (`raw_evaluation`) | 365 dias | Mesmo TTL de `chamadas/` |
| Audit logs | 365 dias | TTL field |

Audio é deletado do GCS **imediatamente** após `Concluído` (worker cleanup).

## 5. Seus direitos (LGPD Art. 18)

| Direito | Como exercer |
|---|---|
| **Acesso** | `GET /api/users/me/export` (no Portal) |
| **Exclusão** | `DELETE /api/users/me` (no Portal) |
| **Correção** | Contactar DPO |

Para exercício: contacte o DPO em **viniciusbritor@gmail.com**.

## 6. Compartilhamento

**NÃO compartilhamos** com terceiros, exceto:
- LLMs (DeepSeek, NVIDIA, MiniMax) sob contrato — **PII já mascarada** antes do envio
- Provedor de infraestrutura (Google Cloud) sob contrato

## 7. Segurança

- Criptografia em repouso (GCP default)
- Criptografia em trânsito (TLS 1.3)
- PII mascarada em LLM e logs
- Audit log imutável

## 8. Mudanças nesta política

Mudanças são comunicadas com 30 dias de antecedência.

---

Última atualização: 08/07/2026
Versão: 1.0

**Ver também**:
- `OmniChannel/docs/LGPD_COMPLIANCE.md` (harness global)
- `OmniChannel/docs/LGPD_RETENTION.md` (política de retenção)
- `Coherence_Portal/docs/PRIVACIDADE.md` (política do Portal)
- `core/masker.py` (implementação de PII masking)