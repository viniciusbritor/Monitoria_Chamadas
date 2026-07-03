import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prod_db.sqlite")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT * FROM chamadas")
rows = cursor.fetchall()
print(f"Total rows in chamadas table: {len(rows)}")
for r in rows:
    print(f"\nID: {r['id']}")
    print(f"Status: {r['status']}")
    print(f"Nota: {r['nota']}")
    print(f"Filename: {r['filename']}")
    trans = r['transcricao']
    print(f"Transcricao length: {len(trans) if trans else 0}")
    trans_diarized = r['transcricao_diarizada']
    print(f"Transcricao Diarizada length: {len(trans_diarized) if trans_diarized else 0}")
    if trans_diarized:
        print(f"Transcricao Diarizada snippet:\n{trans_diarized[:300]}...")

conn.close()
