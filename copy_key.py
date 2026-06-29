import sqlite3
import os

local_db = "monitoria_ia.db"

try:
    c2 = sqlite3.connect(local_db)
    key = c2.execute("SELECT value FROM secrets WHERE key='MINIMAX_API_KEY'").fetchone()[0]
    os.system(f"gcloud run services update monitoria-cx --region us-central1 --update-env-vars MINIMAX_API_KEY={key}")
    print("Env var updated successfully!")
except Exception as e:
    print("Error:", e)
