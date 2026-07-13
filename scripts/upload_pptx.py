import json, os, sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOKEN = os.path.expanduser(r"~\.gemini\config\skills\google_calendar_manager\resources\token_drive.json")
FOLDER = "1aNCHHOiQQzquuxzaeQQa8qr3ciZcsfMt"
PPTX = r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\docs\Custos_Projecao.pptx"

with open(TOKEN) as f:
    creds = Credentials.from_authorized_user_info(json.load(f), scopes=["https://www.googleapis.com/auth/drive"])
service = build("drive", "v3", credentials=creds)

old = service.files().list(q=f"name='Custos_Projecao.pptx' and '{FOLDER}' in parents and trashed=false", fields="files(id)").execute()
for f in old.get("files", []):
    service.files().delete(fileId=f["id"]).execute()
    print(f"Deleted old: {f['id']}")

meta = {"name": "Custos_Projecao.pptx", "parents": [FOLDER]}
media = MediaFileUpload(PPTX, mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation")
up = service.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
print(f"PPTX: {up['webViewLink']}")
print(f"Local: {PPTX}")
