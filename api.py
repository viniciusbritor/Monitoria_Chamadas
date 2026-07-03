import os
import sqlite3
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uuid
import shutil
from datetime import datetime
import json
import jwt

# Firebase Admin (substitui Google OAuth direto - agora validamos tokens emitidos pelo Portal)
try:
    import firebase_admin
    from firebase_admin import credentials, auth as fb_auth
    if not firebase_admin._apps:
        _fb_project = os.getenv("FIRESTORE_PROJECT_ID", "coherence-ominichannel-fs")
        firebase_admin.initialize_app(credentials.ApplicationDefault(), {"projectId": _fb_project})
except Exception as _e:
    print(f"Aviso: firebase-admin nao inicializado: {_e}")
    fb_auth = None

from core.transcriber import Transcriber, preload_model
from core.evaluator import Evaluator
from core.portal_auth import is_authorized_for_module, get_user_role_and_admin
from core.portal_audit import log_access_denied

MODULE_ID = "monitoria-chamadas"

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

DB_PATH = "/mnt/db/monitoria_ia.db" if os.path.exists("/mnt/db") else "monitoria_ia.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            name TEXT,
            picture TEXT,
            is_approved BOOLEAN DEFAULT 0,
            role TEXT DEFAULT 'user'
        )
    ''')
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
    except sqlite3.OperationalError:
        pass
        
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_requests (
            token TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            created_at DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chamadas (
            id TEXT PRIMARY KEY,
            filename TEXT,
            uploaded_at DATETIME,
            status TEXT,
            nota INTEGER,
            transcricao TEXT,
            sentimentos_cliente TEXT,
            sentimentos_operador TEXT,
            erros_fatais TEXT,
            raw_evaluation TEXT,
            user_id TEXT,
            diretrizes_qualidade TEXT,
            nota_sentimento_cliente INTEGER,
            nota_qualidade_operador INTEGER,
            transcricao_diarizada TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            checklist_items TEXT,
            estrategia_vendas TEXT,
            estrategia_retencao TEXT
        )
    ''')
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup_event():
    init_db()
    if fb_auth is None:
        print("ERRO CRITICO: firebase-admin nao foi inicializado. Verifique FIRESTORE_PROJECT_ID.", flush=True)
    # Otimizacao C: pre-carregar modelo Whisper no startup
    # Salva ~33s no primeiro upload
    try:
        get_transcriber()
        print("Transcriber pre-carregado no startup", flush=True)
    except Exception as e:
        print(f"AVISO: Falha ao pre-carregar Transcriber: {e}", flush=True)

def get_current_user(authorization: str = Header(None)):
    """Valida Firebase token, valida permissao no Portal, retorna user info."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    try:
        token = authorization.split("Bearer ")[1]
        if fb_auth is None:
            raise HTTPException(status_code=503, detail="firebase-admin nao disponivel no servidor")
        decoded = fb_auth.verify_id_token(token)
        email = decoded.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Token sem email")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase token: {e}")

    # Valida permissao no Portal (source of truth)
    if not is_authorized_for_module(email, MODULE_ID):
        # Registra acesso negado no audit log do Portal (fire-and-forget)
        log_access_denied(MODULE_ID, token, f"Tentativa de acesso ao modulo '{MODULE_ID}' negada")
        raise HTTPException(status_code=403, detail=f"Acesso negado: {email} nao tem permissao para '{MODULE_ID}'")

    # Decora user com role info vinda do Portal
    role_info = get_user_role_and_admin(email)
    decoded["is_super_admin"] = role_info["is_super_admin"]
    decoded["client_id"] = role_info["client_id"]
    decoded["role"] = "admin" if role_info["is_super_admin"] else "user"
    return decoded

def save_user(user_info):
    pass # Usuários agora são salvos no banco global do SSO

# SSO handoff: Portal abre Monitoria com ?token=<jwt> e Monitoria valida + cria sessao
@app.post("/api/auth/portal-sso")
def portal_sso(token: str = Form(...)):
    """Valida Firebase token vindo do Portal e cria sessao local."""
    if fb_auth is None:
        raise HTTPException(status_code=503, detail="firebase-admin nao disponivel")
    try:
        decoded = fb_auth.verify_id_token(token)
        email = decoded.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Token sem email")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase token: {e}")

    # Verifica permissao
    if not is_authorized_for_module(email, MODULE_ID):
        log_access_denied(MODULE_ID, token, "Tentativa de SSO Portal sem permissao")
        raise HTTPException(status_code=403, detail=f"Acesso negado: {email} sem permissao para '{MODULE_ID}'")

    role_info = get_user_role_and_admin(email)
    return {
        "email": email,
        "name": decoded.get("name"),
        "picture": decoded.get("picture"),
        "role": "admin" if role_info["is_super_admin"] else "user",
        "is_super_admin": role_info["is_super_admin"],
        "token": token,
    }

transcriber = None
evaluator = None

def get_transcriber():
    """Retorna Transcriber pre-carregado no startup."""
    global transcriber
    if transcriber is None:
        transcriber = Transcriber()
    return transcriber

def get_evaluator():
    """Retorna Evaluator (carga lazy para nao atrasar startup)."""
    global evaluator
    if evaluator is None:
        evaluator = Evaluator()
    return evaluator

def process_call_task(call_id: str, file_path: str, user_id: str, diretrizes_qualidade: str):
    def update_status(status_text):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE chamadas SET status = ? WHERE id = ?", (status_text, call_id))
        conn.commit()
        conn.close()

    try:
        # Busca configurações do usuário
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,))
        settings_row = cursor.fetchone()
        conn.close()
        
        user_settings = {}
        if settings_row:
            user_settings = dict(settings_row)

        # Etapa 1: Transcrição Bruta
        update_status("Transcrevendo Áudio (Whisper)...")
        raw_transcript, segments = get_transcriber().transcribe(file_path)
        
        # Etapa 2: Diarização IA
        update_status("Separando falas (Diarização MiniMax)...")
        diarized_transcript = get_evaluator().diarize(raw_transcript)
        
        # Etapa 3: Avaliação IA
        update_status("Analisando Qualidade e Sentimento (MiniMax M3)...")
        evaluation = get_evaluator().evaluate(diarized_transcript, user_settings=user_settings, pop_context="", quality_form=diretrizes_qualidade)
        
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

@app.post("/api/request-access")
async def request_access(email: str = Form(...)):
    token = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("INSERT OR REPLACE INTO access_requests (token, email, created_at) VALUES (?, ?, ?)", (token, email, now))
    conn.commit()
    conn.close()
    
    # Simula envio de e-mail por enquanto (MOCK)
    approve_url = f"https://monitoria-cx-4105010761.us-central1.run.app/api/approve-access?token={token}"
    print(f"\n============================================\n[NOVO PEDIDO DE ACESSO] De: {email}\n[CLIQUE AQUI PARA APROVAR]: {approve_url}\n============================================\n", flush=True)
    return {"message": "Solicitação enviada. O administrador foi notificado!"}

@app.get("/api/approve-access")
async def approve_access(token: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM access_requests WHERE token = ?", (token,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"message": "Token inválido ou expirado."}
    
    email = row[0]
    cursor.execute("INSERT OR IGNORE INTO users (id, email, is_approved) VALUES (?, ?, 1)", (str(uuid.uuid4()), email))
    cursor.execute("UPDATE users SET is_approved = 1 WHERE email = ?", (email,))
    cursor.execute("DELETE FROM access_requests WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return {"message": f"Acesso aprovado para {email} com sucesso!"}

class UserSettings(BaseModel):
    checklist_items: str
    estrategia_vendas: str
    estrategia_retencao: str

@app.get("/api/settings")
def get_settings(user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user.get("sub"),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "checklist_items": "[]",
        "estrategia_vendas": "",
        "estrategia_retencao": ""
    }

@app.post("/api/settings")
def save_settings(settings: UserSettings, user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO user_settings (user_id, checklist_items, estrategia_vendas, estrategia_retencao)
        VALUES (?, ?, ?, ?)
    ''', (user.get("sub"), settings.checklist_items, settings.estrategia_vendas, settings.estrategia_retencao))
    conn.commit()
    conn.close()
    return {"message": "Configurações salvas com sucesso"}

@app.get("/api/calls")
def get_calls(user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename, uploaded_at, status, nota, nota_sentimento_cliente, nota_qualidade_operador, raw_evaluation FROM chamadas WHERE user_id = ? ORDER BY uploaded_at DESC", (user.get("sub"),))
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
    background_tasks.add_task(process_call_task, call_id, file_path, user.get("sub"), diretrizes)
    
    return {"message": "Processamento iniciado", "id": call_id}

# Endpoints administrativos migrados para o Coherence Portal (SSO Global).

# Frontend estático (Vite Build) - DEVE FICAR NO FINAL PARA NÃO SOBRESCREVER ROTAS /API
FRONTEND_DIR = os.path.join("frontend", "dist")
ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")

if os.path.exists(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

from fastapi.responses import FileResponse

@app.get("/")
@app.get("/index.html")
async def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        response = FileResponse(index_path)
        # Força o navegador a nunca fazer cache do index.html para garantir atualizações automáticas de UI
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return {"message": "Index HTML not found"}

@app.get("/{file_name}")
async def serve_root_file(file_name: str):
    file_path = os.path.join(FRONTEND_DIR, file_name)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")
