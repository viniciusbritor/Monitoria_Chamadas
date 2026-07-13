import firebase_admin, os, json, requests, sys
from firebase_admin import credentials, auth

key_path = "_fb_key.json"
if not os.path.exists(key_path):
    key_path = os.path.join(os.path.dirname(__file__), "_fb_key.json")

cred = credentials.Certificate(key_path)
firebase_admin.initialize_app(cred, {"projectId": "coherence-ominichannel-fs"})

custom = auth.create_custom_token("viniciusbritor@gmail.com", {"email": "viniciusbritor@gmail.com"})
ct = custom.decode("utf-8") if isinstance(custom, bytes) else custom

FIREBASE_API_KEY = "AIzaSyAIMGRNFUIBBueB8xk0jlTWA-EfpdjywDQ"
resp = requests.post(
    f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={FIREBASE_API_KEY}",
    json={"token": ct, "returnSecureToken": True},
)
data = resp.json()
if "idToken" in data:
    token = data["idToken"]
    out_path = os.path.join(os.path.dirname(__file__), "..", "_token.txt")
    with open(out_path, "w") as f:
        f.write(token)
    print("OK: token salvo em _token.txt")
else:
    print("ERRO:", json.dumps(data, indent=2), file=sys.stderr)
    sys.exit(1)
