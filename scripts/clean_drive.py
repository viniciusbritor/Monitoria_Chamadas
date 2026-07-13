import json, os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TKN = os.path.expanduser(r"~\.gemini\config\skills\google_calendar_manager\resources\token_drive.json")
CUSTOS = "1Nb_OLbJS0012keYcXW58EMz4F1evMz6w"

with open(TKN) as f:
    cr = Credentials.from_authorized_user_info(json.load(f), scopes=["https://www.googleapis.com/auth/drive"])
svc = build("drive", "v3", credentials=cr)

for nm in ["Custos_OmniChannel_Executivo.xlsx", "Custos_Projecao_OmniChannel.pptx"]:
    r = svc.files().list(q=f"name='{nm}' and '{CUSTOS}' in parents and trashed=false", fields="files(id,name)").execute()
    for f in r.get("files", []):
        svc.files().delete(fileId=f["id"]).execute()
        print(f"Deleted: {nm}")

print("Done")
