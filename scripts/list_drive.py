import json, os, sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

token_path = os.path.expanduser(r"~\.gemini\config\skills\google_calendar_manager\resources\token_drive.json")
with open(token_path) as f:
    creds_data = json.load(f)

creds = Credentials.from_authorized_user_info(creds_data, scopes=["https://www.googleapis.com/auth/drive"])
service = build("drive", "v3", credentials=creds)

def list_folder(folder_id, indent=""):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType, size, createdTime)",
        pageSize=50,
    ).execute()
    files = results.get("files", [])
    for f in files:
        is_dir = f["mimeType"] == "application/vnd.google-apps.folder"
        size = f.get("size", "-")
        if size != "-":
            sz = int(size)
            size_str = f"{sz/1024:.1f} KB" if sz < 1048576 else f"{sz/1048576:.1f} MB"
        else:
            size_str = "-"
        print(f"{indent}[{'DIR' if is_dir else 'FILE'}] {f['name']}  ({size_str})")
        if is_dir and indent == "":
            list_folder(f["id"], "  +-- ")
    return files

FOLDER_ID = "1aNCHHOiQQzquuxzaeQQa8qr3ciZcsfMt"

folder = service.files().get(fileId=FOLDER_ID, fields="name,createdTime,owners").execute()
print(f"Pasta: {folder.get('name')}")
print(f"Dono: {folder['owners'][0].get('emailAddress')}")
print()
list_folder(FOLDER_ID)
