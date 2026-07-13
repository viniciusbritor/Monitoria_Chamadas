"""Create Custos/ folder, upload dated versions, clean root"""
import json, os
from datetime import date
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TKN = os.path.expanduser(r"~\.gemini\config\skills\google_calendar_manager\resources\token_drive.json")
ROOT = "1aNCHHOiQQzquuxzaeQQa8qr3ciZcsfMt"
TODAY = date.today().isoformat()

with open(TKN) as f:
    cr = Credentials.from_authorized_user_info(json.load(f), scopes=["https://www.googleapis.com/auth/drive"])
svc = build("drive", "v3", credentials=cr)

# 1. Create/get Custos folder
existing = svc.files().list(
    q=f"name='Custos' and '{ROOT}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
    fields="files(id)"
).execute()
if existing.get("files"):
    CUSTOS = existing["files"][0]["id"]
    print(f"Pasta Custos ja existe: {CUSTOS}")
else:
    created = svc.files().create(body={
        "name": "Custos", "mimeType": "application/vnd.google-apps.folder", "parents": [ROOT]
    }, fields="id").execute()
    CUSTOS = created["id"]
    print(f"Pasta Custos criada: {CUSTOS}")

# 2. Upload dated versions
files = [
    (r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\docs\Custos_OmniChannel_Executivo.xlsx",
     f"Custos_OmniChannel_{TODAY}.xlsx",
     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    (r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\docs\Custos_Projecao_OmniChannel.pptx",
     f"Custos_Projecao_OmniChannel_{TODAY}.pptx",
     "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
]

for local, name, mime in files:
    old = svc.files().list(q=f"name='{name}' and '{CUSTOS}' in parents and trashed=false", fields="files(id)").execute()
    for f in old.get("files", []):
        svc.files().delete(fileId=f["id"]).execute()
    media = MediaFileUpload(local, mimetype=mime)
    up = svc.files().create(body={"name": name, "parents": [CUSTOS]}, media_body=media, fields="id,webViewLink").execute()
    print(f"  {name}")

# 3. Clean root from old files
for nm in ["Custos_OmniChannel_Executivo.xlsx", "Custos_Projecao_OmniChannel.pptx",
           "Custos_500_Calls_Day.xlsx", "Custos_Projecao_Completa.xlsx",
           "Custos_Projecao_Final.pptx", "Custos_Projecao_v2.pptx"]:
    old = svc.files().list(q=f"name='{nm}' and '{ROOT}' in parents and trashed=false", fields="files(id)").execute()
    for f in old.get("files", []):
        svc.files().delete(fileId=f["id"]).execute()
        print(f"  Deleted root: {nm}")

print(f"\nDone: https://drive.google.com/drive/folders/{CUSTOS}")
