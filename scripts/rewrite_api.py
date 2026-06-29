import os

API_PATH = "api.py"

with open(API_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# We need to add Google Auth verification and the new upload flow.
# Let's replace the whole file for safety to include auth dependencies and the new logic.

NEW_API = """import os
import sqlite3
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uuid
import shutil
from datetime import datetime
import json
from google.oauth2 import id_token
from google.auth.transport import requests

from core.transcriber import Transcriber
from core.evaluator import Evaluator

app = FastAPI(title="Monitoria de Chamadas API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

DB_PATH = "monitoria_ia.db"

# Substitua pelo seu Google Client ID real depois
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    try:
        token = authorization.split("Bearer ")[1]
        if not GOOGLE_CLIENT_ID:
            # Bypass para desenvolvimento se Client ID não configurado
            return {"email": "dev@coherence.ai", "name": "Dev User", "sub": "dev-123"}
            
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)
        return idinfo
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Token: {str(e)}")

def save_user(user_info):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (id, email, name, picture)
        VALUES (?, ?, ?, ?)
    ''', (user_info.get("sub"), user_info.get("email"), user_info.get("name"), user_info.get("picture")))
    conn.commit()
    conn.close()

transcriber = Transcriber()
evaluator = Evaluator()

def process_call_task(call_id: str, file_path: str, diretrizes_qualidade: str):
    def update_status(status_text):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE chamadas SET status = ? WHERE id = ?", (status_text, call_id))
        conn.commit()
        conn.close()

    try:
        # Etapa 1: Transcrição Bruta
        update_status("Transcrevendo Áudio (Whisper)...")
        raw_transcript, segments = transcriber.transcribe(file_path)
        
        # Etapa 2: Diarização IA
        update_status("Separando falas (Diarização MiniMax)...")
        diarized_transcript = evaluator.diarize(raw_transcript)
        
        # Etapa 3: Avaliação IA
        update_status("Analisando Qualidade e Sentimento (MiniMax M3)...")
        evaluation = evaluator.evaluate(diarized_transcript, quality_form=diretrizes_qualidade)
        
        # Etapa 4: Conclusão
        nota = evaluation.get("nota_geral")
        if isinstance(nota, str) and "%" in nota:
            nota = int(nota.replace("%", "").strip())
        elif isinstance(nota, (int, float)):
            nota = int(nota)
        else:
            nota = 0
            
        nota_sentimento_cliente = evaluation.get("nota_sentimento_cliente", 5)
        nota_qualidade_operador = evaluation.get("nota_qualidade_operador", nota)
            
        sentimentos_cliente = json.dumps(evaluation.get("sentimentos_cliente", []))
        sentimentos_operador = json.dumps(evaluation.get("sentimentos_operador", []))
        erros_fatais = json.dumps(evaluation.get("erros_fatais_identificados", []))
        raw_evaluation = json.dumps(evaluation)
        transcricao = json.dumps(segments)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE chamadas
            SET status = ?, nota = ?, transcricao = ?, sentimentos_cliente = ?, sentimentos_operador = ?, erros_fatais = ?, raw_evaluation = ?, transcricao_diarizada = ?, nota_sentimento_cliente = ?, nota_qualidade_operador = ?
            WHERE id = ?
        ''', ("Concluído", nota, transcricao, sentimentos_cliente, sentimentos_operador, erros_fatais, raw_evaluation, diarized_transcript, nota_sentimento_cliente, nota_qualidade_operador, call_id))
        conn.commit()
        conn.close()
        
    except Exception as e:
        update_status(f"Erro: {str(e)}")

@app.get("/api/auth/me")
def get_me(user = Depends(get_current_user)):
    save_user(user)
    return user

@app.get("/api/calls")
def get_calls(user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename, uploaded_at, status, nota, nota_sentimento_cliente, nota_qualidade_operador FROM chamadas WHERE user_id = ? ORDER BY uploaded_at DESC", (user.get("sub"),))
    calls = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return calls

@app.get("/api/calls/{call_id}")
def get_call(call_id: str, user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chamadas WHERE id = ? AND user_id = ?", (call_id, user.get("sub")))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Chamada não encontrada ou sem permissão")
    
    call_data = dict(row)
    for field in ["transcricao", "sentimentos_cliente", "sentimentos_operador", "erros_fatais", "raw_evaluation"]:
        if call_data.get(field):
            try:
                call_data[field] = json.loads(call_data[field])
            except:
                pass
    return call_data

@app.post("/api/upload")
async def upload_audio(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    diretrizes: str = Form(""),
    user = Depends(get_current_user)
):
    call_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{call_id}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO chamadas (id, filename, uploaded_at, status, user_id, diretrizes_qualidade)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (call_id, file.filename, now, "Na Fila de Processamento...", user.get("sub"), diretrizes))
    conn.commit()
    conn.close()
    
    # Aciona processo assíncrono
    background_tasks.add_task(process_call_task, call_id, file_path, diretrizes)
    
    return {"message": "Processamento iniciado", "id": call_id}

# Frontend estático (Vite Build) - DEVE FICAR NO FINAL PARA NÃO SOBRESCREVER ROTAS /API
FRONTEND_DIR = os.path.join("frontend", "dist")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
"""

with open(API_PATH, "w", encoding="utf-8") as f:
    f.write(NEW_API)

print("api.py atualizado com sucesso!")
