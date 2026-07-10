"""
core/db.py - Firestore wrapper para Monitoria de Chamadas (substitui SQLite GCS FUSE).

Motivation:
- SQLite via GCS FUSE compartilhado mostrou 4 bugs insuperaveis:
  1. BufferedWriteHandler.OutOfOrderError no journal file
  2. stale file handle (concurrent writers)
  3. file was clobbered due to generation/metageneration mismatch
  4. disk I/O error (FUSE cache invalidation)
- Firestore oferece:
  - Gerenciado (zero I/O race conditions)
  - Concorrencia via last-write-wins (timestamped writes)
  - Queries indexadas (status, user_id, uploaded_at)
  - Sem volume mount / sem cold-start I/O

Collection schema:
  collection: chamadas
  documentId: <call_id uuid>
  fields:
    filename (string)
    uploaded_at (timestamp)
    status (string)
    nota (number | null)
    transcricao (string | null)  # JSON serialized
    transcricao_diarizada (string | null)
    sentimentos_cliente (string | null)  # JSON serialized
    sentimentos_operador (string | null)  # JSON serialized
    erros_fatais (string | null)  # JSON serialized
    raw_evaluation (string | null)  # JSON serialized
    user_id (string)
    diretrizes_qualidade (string | null)
    nota_sentimento_cliente (number | null)
    nota_qualidade_operador (number | null)
    gcs_uri (string | null)
    audio_duration_sec (number | null)
    progress_pct (number | null)
    created_at (timestamp)
    updated_at (timestamp)

Locking policy: LAST-WRITE-WINS (sem transactions).
  - Worker e unico writer de status (callback de progress).
  - test-env callback e unico writer de nota/raw_evaluation.
  - Conflitos sao raros e benignos (1-2s de sobreposicao de update).

Indexes necessarios (composite):
  - status ASC, uploaded_at DESC  (dashboard)
  - user_id ASC, uploaded_at DESC  (historico por usuario)

Autor: vinicius + claude-code-assistant
Data: 2026-07-06 (migracao de SQLite GCS FUSE para Firestore)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)

# Constantes
COLLECTION_NAME = "chamadas"
DEFAULT_PROJECT = "coherence-ominichannel-fs"

# Whitelist de campos que podem ser escritos em update (segurança contra injection de keys extras)
WRITABLE_FIELDS = frozenset({
    "filename", "uploaded_at", "status", "nota", "transcricao",
    "transcricao_diarizada", "sentimentos_cliente", "sentimentos_operador",
    "erros_fatais", "raw_evaluation", "user_id", "diretrizes_qualidade",
    "nota_sentimento_cliente", "nota_qualidade_operador", "gcs_uri",
    "audio_duration_sec", "progress_pct",
})


class ChamadasDB:
    """Wrapper Firestore para a collection `chamadas`. (existente)"""
    """Wrapper Firestore para a collection `chamadas`.

    Filosofia: last-write-wins, sem locks, sem transactions. A natureza
    append-only do pipeline (status sempre progride para frente) torna
    conflitos raros. UI polling de 2s absorve pequenas sobreposições.

    Lazy client: a primeira chamada cria o client Firestore (com credentials
    ADC do Cloud Run service account). Subsequentes reusam.
    """

    _instance: Optional["ChamadasDB"] = None
    _client: Optional[firestore.Client] = None

    def __new__(cls):
        # Singleton para reusar o client Firestore entre chamadas
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_local()
        return cls._instance

    def _init_local(self):
        self._project_id = os.getenv("FIRESTORE_PROJECT_ID", DEFAULT_PROJECT)
        self._collection_name = os.getenv("FIRESTORE_COLLECTION", COLLECTION_NAME)
        # client lazy

    @property
    def _db(self) -> firestore.Client:
        if self._client is None:
            self._client = firestore.Client(project=self._project_id)
        return self._client

    @property
    def collection(self):
        return self._db.collection(self._collection_name)

    # ========================================================================
    # CRUD basico
    # ========================================================================

    def create(self, call_id: str, fields: Dict[str, Any]) -> None:
        """Cria uma chamada. Falha se ja existir (use update_or_create para upsert)."""
        sanitized = self._sanitize(fields)
        sanitized["created_at"] = firestore.SERVER_TIMESTAMP
        sanitized["updated_at"] = firestore.SERVER_TIMESTAMP
        sanitized["call_id"] = call_id  # mirrored inside doc for queries
        self.collection.document(call_id).create(sanitized)

    def update_or_create(self, call_id: str, fields: Dict[str, Any]) -> None:
        """Upsert: cria se nao existir, atualiza se existir (last-write-wins)."""
        sanitized = self._sanitize(fields)
        sanitized["updated_at"] = firestore.SERVER_TIMESTAMP
        sanitized["call_id"] = call_id
        self.collection.document(call_id).set(sanitized, merge=True)

    def get(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Retorna a chamada como dict ou None se nao existir."""
        doc = self.collection.document(call_id).get()
        if not doc.exists:
            return None
        return doc.to_dict()

    def update(self, call_id: str, fields: Dict[str, Any]) -> bool:
        """Atualiza campos especificos. Retorna False se chamada nao existir."""
        sanitized = self._sanitize(fields)
        sanitized["updated_at"] = firestore.SERVER_TIMESTAMP
        doc_ref = self.collection.document(call_id)
        if not doc_ref.get().exists:
            return False
        doc_ref.update(sanitized)
        return True

    def delete(self, call_id: str) -> bool:
        """Remove uma chamada. Retorna False se nao existir."""
        doc_ref = self.collection.document(call_id)
        if not doc_ref.get().exists:
            return False
        doc_ref.delete()
        return True

    # ========================================================================
    # Queries
    # ========================================================================

    def list_all(self, limit: int = 100, status_filter: Optional[str] = None,
                 user_id_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista chamadas, mais recentes primeiro. Opcionalmente filtra por status/user_id.

        ATENCAO: filtros nao-indexaveis fazem scan completo (caro para N grande).
        Para producao, prefira list_by_user_id() ou list_by_status().
        """
        q = self.collection.order_by("uploaded_at", direction=firestore.Query.DESCENDING).limit(limit)
        if status_filter:
            q = q.where("status", ">=", status_filter).where("status", "<", status_filter + "\uf8ff")
        if user_id_filter:
            q = q.where("user_id", "==", user_id_filter)
        result = []
        for doc in q.stream():
            d = doc.to_dict()
            d["id"] = doc.id
            result.append(d)
        return result

    def list_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        """Busca multiplas chamadas por IDs. Usa batch get (mais eficiente que N queries)."""
        if not ids:
            return []
        refs = [self.collection.document(cid) for cid in ids]
        docs = self._db.get_all(refs)
        result = []
        for doc in docs:
            if doc.exists:
                d = doc.to_dict()
                d["id"] = doc.id
                result.append(d)
        return result

    def list_by_status(self, status_prefix: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Lista chamadas em status que COMECAM COM prefix. Usa indice status+uploaded_at."""
        # Firestore nao suporta prefix match nativo. Solucao: usar range query com sentinel.
        q = self.collection.where(
            "status", ">=", status_prefix
        ).where(
            "status", "<", status_prefix + "\uf8ff"
        ).order_by("status").order_by(
            "uploaded_at", direction=firestore.Query.DESCENDING
        ).limit(limit)
        return [doc.to_dict() for doc in q.stream()]

    def list_stale(self, older_than_seconds: int, status_prefixes: tuple = (
            "Na Fila", "Transcrevendo", "Separando", "Analisando"
    )) -> List[Dict[str, Any]]:
        """Lista chamadas em status inicial mais velhas que threshold (orphans)."""
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
        # NEW (08/07/2026): uploaded_at e' armazenado como STRING ISO (nao timestamp Firestore).
        # Para query por tempo, converter cutoff para string ISO e comparar lexicograficamente.
        cutoff_str = cutoff.isoformat()
        all_stale = []
        for prefix in status_prefixes:
            q = (self.collection
                 .where("status", ">=", prefix)
                 .where("status", "<", prefix + "\uf8ff")
                 .where("uploaded_at", "<", cutoff_str))
            all_stale.extend([doc.to_dict() for doc in q.stream()])
        return all_stale

    def cleanup_orphans(self, older_than_seconds: int, new_status: str) -> List[str]:
        """Marca orphans como erro. Retorna IDs atualizados."""
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
        cutoff_str = cutoff.isoformat()
        updated_ids = []
        for prefix in ("Na Fila", "Transcrevendo", "Separando", "Analisando"):
            q = (self.collection
                 .where("status", ">=", prefix)
                 .where("status", "<", prefix + "\uf8ff")
                 .where("uploaded_at", "<", cutoff_str))
            for doc in q.stream():
                doc.reference.update({
                    "status": new_status,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                })
                updated_ids.append(doc.id)
        return updated_ids

    # ========================================================================
    # Helpers
    # ========================================================================

    def _sanitize(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Remove fields nao permitidos. Converte tipos nao-Firestore para JSON."""
        import json
        sanitized = {}
        for k, v in fields.items():
            if k not in WRITABLE_FIELDS:
                logger.warning(f"db._sanitize ignorando field nao-writable: {k}")
                continue
            # JSON-serializar listas e dicts (Firestore nao suporta nested sem typed schema)
            if isinstance(v, (list, dict)) and not isinstance(v, str):
                sanitized[k] = json.dumps(v, ensure_ascii=False)
            else:
                sanitized[k] = v
        return sanitized


# Singleton global
_db_instance: Optional[ChamadasDB] = None


def get_db() -> ChamadasDB:
    """Retorna singleton da ChamadasDB."""
    global _db_instance
    if _db_instance is None:
        _db_instance = ChamadasDB()
    return _db_instance


# ============================================================================
# Backwards-compat: API legada sqlite-like para minimizar mudancas em api.py/worker.py
# ============================================================================

def init_db():
    """No-op mantido para compat. Firestore nao precisa de schema initialization
    (collections sao criadas lazily). Indices sao provisionados via terraform/gcloud.
    """
    logger.info("init_db: no-op (Firestore gerenciado). Indices devem ser criados via cloudbuild-firestore-indexes.yaml.")


def get_call(call_id: str) -> Optional[Dict[str, Any]]:
    return get_db().get(call_id)


def list_calls(limit: int = 100, status_filter: Optional[str] = None,
               user_id_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    return get_db().list_all(limit=limit, status_filter=status_filter, user_id_filter=user_id_filter)


def list_calls_by_ids(ids: List[str]) -> List[Dict[str, Any]]:
    """Busca multiplas chamadas por IDs."""
    return get_db().list_by_ids(ids)


def update_call_status(call_id: str, status: str, **extra_fields) -> bool:
    """Compat helper: update do campo status + extras."""
    fields = {"status": status}
    fields.update(extra_fields)
    return get_db().update(call_id, fields)


def cleanup_orphans(older_than_seconds: int = 1800,
                     new_status: str = "Erro: orfao, reenviar") -> List[str]:
    return get_db().cleanup_orphans(older_than_seconds, new_status)


# ============================================================================
# UserSettingsDB — collection separada para QA settings por usuario
# ============================================================================
# Migrado de SQLite (tabela user_settings) em 06/07/2026.
# DocumentId = user_id (Firebase sub) — assim um get por user_id e' O(1).
# Campos:
#   checklist_items (string, JSON-serializado) - lista de itens do POP
#   estrategia_vendas (string) - playbook de up-sell/cross-sell
#   estrategia_retencao (string) - playbook anti-cancelamento
#   updated_at (timestamp Firestore)
#
# Locking policy: last-write-wins. Conflitos raros (user edita em 1 aba).
# Indices: nao requer composto (query e' sempre por documentId).
# ============================================================================

USER_SETTINGS_COLLECTION = "user_settings"
USER_SETTINGS_WRITABLE = frozenset({
    "checklist_items", "estrategia_vendas", "estrategia_retencao",
})


class UserSettingsDB:
    """Wrapper Firestore para a collection `user_settings`.

    DocumentId = user_id (Firebase sub) para lookup O(1).
    Singleton via get_user_settings_db().
    """

    _instance: Optional["UserSettingsDB"] = None
    _client: Optional[firestore.Client] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_local()
        return cls._instance

    def _init_local(self):
        self._project_id = os.getenv("FIRESTORE_PROJECT_ID", DEFAULT_PROJECT)
        self._collection_name = os.getenv("FIRESTORE_COLLECTION_USER_SETTINGS", USER_SETTINGS_COLLECTION)

    @property
    def _db(self) -> firestore.Client:
        if self._client is None:
            self._client = firestore.Client(project=self._project_id)
        return self._client

    @property
    def collection(self):
        return self._db.collection(self._collection_name)

    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retorna settings do user ou None se nao existir."""
        doc = self.collection.document(user_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        data["user_id"] = user_id
        return data

    def upsert(self, user_id: str, fields: Dict[str, Any]) -> bool:
        """Cria ou atualiza settings. Sanitiza contra key injection. Retorna True."""
        sanitized = {}
        for k, v in fields.items():
            if k not in USER_SETTINGS_WRITABLE:
                logger.warning(f"UserSettingsDB.upsert ignorando field nao-writable: {k}")
                continue
            sanitized[k] = v
        sanitized["updated_at"] = firestore.SERVER_TIMESTAMP
        self.collection.document(user_id).set(sanitized, merge=True)
        return True


_user_settings_instance: Optional[UserSettingsDB] = None


def get_user_settings_db() -> UserSettingsDB:
    """Retorna singleton da UserSettingsDB."""
    global _user_settings_instance
    if _user_settings_instance is None:
        _user_settings_instance = UserSettingsDB()
    return _user_settings_instance


def get_user_settings(user_id: str) -> Optional[Dict[str, Any]]:
    """Helper: retorna settings do user ou None."""
    return get_user_settings_db().get(user_id)


def upsert_user_settings(user_id: str, fields: Dict[str, Any]) -> bool:
    """Helper: upsert settings do user."""
    return get_user_settings_db().upsert(user_id, fields)
