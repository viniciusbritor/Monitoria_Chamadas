"""
migrate_firestore_status_accent.py
==================================

One-shot: normalizar status 'Concluido' (sem acento) -> 'Concluído' (com acento)
para todas as chamadas existentes no Firestore.

Resolve loop de polling/reprocessamento para dados legados (pre-07/07/2026)
onde o worker gravava 'Concluido' (typo) mas o Dashboard.jsx comparava com
'Concluído' (com acento). Resultado: UI nunca reconhecia conclusao, e o
worker reprocessava toda vez que Pub/Sub redeliverava.

Idempotente: pode rodar multiplas vezes sem efeito colateral.

Uso:
  python scripts/migrate_firestore_status_accent.py

Pre-requisitos:
- GOOGLE_APPLICATION_CREDENTIALS configurado (ou rodando no Cloud Run Job)
- FIRESTORE_PROJECT_ID=coherence-ominichannel-fs (default)

Autor: vinicius + claude-code-assistant
Data: 2026-07-07 (Plano A++ follow-up: fix bug de acentuacao)
"""
import os
import sys
from google.cloud import firestore

PROJECT_ID = os.getenv("FIRESTORE_PROJECT_ID", "coherence-ominichannel-fs")
COLLECTION = os.getenv("FIRESTORE_COLLECTION", "chamadas")

# Variantes que devem ser normalizadas para a forma canonica
VARIANTS = {
    "Concluido": "Concluído",       # sem acento (typo historico)
    "concluido": "Concluído",       # lowercase
    "concluído": "Concluído",       # lowercase com acento
    "CONCLUIDO": "Concluído",       # uppercase
    "CONCLUÍDO": "Concluído",       # uppercase com acento
}


def main():
    print(f"[Migrate] Conectando ao Firestore: project={PROJECT_ID} collection={COLLECTION}")
    db = firestore.Client(project=PROJECT_ID)
    collection = db.collection(COLLECTION)

    migrated = 0
    scanned = 0
    skipped = 0
    errors = 0

    for doc in collection.stream():
        scanned += 1
        try:
            data = doc.to_dict() or {}
            current_status = data.get("status", "")
            if current_status in VARIANTS:
                new_status = VARIANTS[current_status]
                doc.reference.update({"status": new_status})
                migrated += 1
                print(
                    f"[Migrate] {doc.id[:8]}... status: "
                    f"{current_status!r} -> {new_status!r} (filename={data.get('filename', '?')})",
                    flush=True,
                )
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            print(f"[Migrate] ERRO no doc {doc.id}: {e}", flush=True)

    print("")
    print("=" * 60)
    print(f"[Migrate] Resumo:")
    print(f"  Scanned:   {scanned} documentos")
    print(f"  Migrated:  {migrated} (status normalizado)")
    print(f"  Skipped:   {skipped} (ja' estava canonico)")
    print(f"  Errors:    {errors}")
    print("=" * 60)

    if errors > 0:
        print(f"[Migrate] ATENCAO: {errors} erros. Revisar logs acima.")
        sys.exit(1)
    elif migrated == 0:
        print("[Migrate] Nada para migrar. Firestore ja' esta' canonico.")
    else:
        print(f"[Migrate] Sucesso. {migrated} documentos normalizados.")
    sys.exit(0)


if __name__ == "__main__":
    main()
