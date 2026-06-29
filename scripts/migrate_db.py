import sqlite3

DB_PATH = "monitoria_ia.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            name TEXT,
            picture TEXT
        )
    ''')
    
    # Add columns to chamadas
    new_columns = [
        ("user_id", "TEXT"),
        ("diretrizes_qualidade", "TEXT"),
        ("nota_sentimento_cliente", "INTEGER"),
        ("nota_qualidade_operador", "INTEGER"),
        ("transcricao_diarizada", "TEXT")
    ]
    
    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE chamadas ADD COLUMN {col_name} {col_type}")
            print(f"Added column {col_name}")
        except sqlite3.OperationalError as e:
            # Column probably already exists
            print(f"Skipped {col_name}: {e}")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
