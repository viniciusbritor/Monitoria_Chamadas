import os
import sqlite3
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Configurações do Banco de Dados
DB_NAME = "monitoria_ia.db"

def _ensure_table():
    """Garante que a tabela secrets existe no banco SQLite."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS secrets (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            descricao  TEXT,
            updated_at DATETIME DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()

# Caminho do Banco de Secrets Centralizado (Compartilhado)
CENTRAL_DB_PATH = r"C:\Users\vinic\brasil_ai.db"

def get_secret(key, default=""):
    """
    Retorna o valor de uma secret. 
    Prioridade: 
      1. GCP Secret Manager (se em nuvem)
      2. SQLite Local (monitoria_ia.db)
      3. SQLite Central (brasil_ai.db)
      4. os.getenv (ambiente / .env)
      5. default
    """
    # 1. Tentar GCP Secret Manager
    gcp_project = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if gcp_project:
        try:
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{gcp_project}/secrets/{key}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            val = response.payload.data.decode("utf-8").strip().lstrip("\ufeff")
            if val:
                return val
        except Exception:
            pass

    _ensure_table()
    
    # 2. Tentar SQLite Local do Projeto
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM secrets WHERE key = ?", (key,))
        result = cursor.fetchone()
        conn.close()
        if result and result[0]:
            return result[0].strip().lstrip("\ufeff")
    except Exception as e:
        print(f"Warning: Erro ao ler secret '{key}' do banco local: {e}")

    # 3. Tentar SQLite Centralizado Compartilhado
    if os.path.exists(CENTRAL_DB_PATH):
        try:
            conn = sqlite3.connect(CENTRAL_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM secrets WHERE key = ?", (key,))
            result = cursor.fetchone()
            conn.close()
            if result and result[0]:
                return result[0].strip().lstrip("\ufeff")
        except Exception as e:
            print(f"Warning: Erro ao ler secret '{key}' do banco central: {e}")

    # 4. Fallback os.getenv (carregado via .env)
    env_val = os.getenv(key)
    if env_val:
        return env_val.strip().lstrip("\ufeff")

    # 5. Default
    return default.strip().lstrip("\ufeff") if isinstance(default, str) else default

def set_secret(key, value, descricao=""):
    """Define ou atualiza uma secret no banco SQLite."""
    _ensure_table()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO secrets (key, value, descricao, updated_at)
        VALUES (?, ?, ?, datetime('now','localtime'))
    """, (key, value, descricao))
    conn.commit()
    conn.close()
    print(f"✅ Secret '{key}' salva com sucesso.")

def list_secrets():
    """Lista as chaves disponíveis (sem mostrar o valor completo por segurança)."""
    _ensure_table()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT key, descricao, updated_at FROM secrets")
    rows = cursor.fetchall()
    conn.close()
    
    print("\n--- Secrets Disponíveis ---")
    if not rows:
        print("Nenhuma secret cadastrada.")
    for row in rows:
        print(f"🔑 {row[0]} - {row[1]} (Atualizado em: {row[2]})")
    print("---------------------------\n")

def migrate_from_env():
    """Migra as chaves do .env para o SQLite."""
    load_dotenv()
    
    # Mapeamento das chaves do projeto
    secrets_map = {
        "GEMINI_API_KEY": "Google Gemini API Key para Avaliação",
        "DATABASE_URL": "URL do Banco de Dados Principal",
        "WHISPER_MODEL": "Modelo do Whisper a ser usado (base, small, medium, large-v3)",
    }
    
    print("Iniciando migração do .env para SQLite...")
    for key, desc in secrets_map.items():
        val = os.getenv(key)
        if val:
            set_secret(key, val, desc)
        else:
            print(f"⚠️ Chave '{key}' não encontrada no .env")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gerenciador de Secrets Monitoria IA")
    parser.add_argument("--migrate", action="store_true", help="Migra chaves do .env para o banco")
    parser.add_argument("--list", action="store_true", help="Lista chaves cadastradas")
    parser.add_argument("--get", type=str, help="Busca o valor de uma chave (mostra apenas final)")
    parser.add_argument("--set", nargs=3, metavar=('KEY', 'VALUE', 'DESC'), help="Define uma nova secret")
    
    args = parser.parse_args()
    
    if args.migrate:
        migrate_from_env()
    elif args.list:
        list_secrets()
    elif args.get:
        val = get_secret(args.get)
        if val:
            print(f"Valor de '{args.get}': {'*' * (len(val)-4) + val[-4:] if len(val) > 4 else val}")
        else:
            print(f"❌ Secret '{args.get}' não encontrada.")
    elif args.set:
        set_secret(args.set[0], args.set[1], args.set[2])
    else:
        parser.print_help()
