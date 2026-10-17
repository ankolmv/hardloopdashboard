"""Cloud-modus (GitHub Actions + GitHub Pages).

Stappen in de workflow:
  python cloud.py restore             # versleutelde cache (state.enc) terugzetten + secrets -> .env / Garmin-token
  python cloud.py action <naam> <json> # optioneel: actie vanaf de website (doel, Garmin-push, zones, instellingen)
  python cloud.py sync                # intervals.icu + Garmin ophalen
  python cloud.py build site          # statische site met versleutelde data
  python cloud.py save                # cache versleuteld opslaan in state.enc

Versleuteling: AES-256-GCM. Site-data met een sleutel uit DASHBOARD_PASSWORD (PBKDF2-SHA256),
cache met STATE_KEY. Zonder die sleutels is niets van de data leesbaar in de publieke repository.
"""
import base64
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import paths

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state", "state.enc")
STATE_ITEMS = ["data", ".garmin_tokens", "goal.json", "settings.json"]
PBKDF2_ITER = 200_000
KM_STEPS = range(0, 101, 5)
PERIODS = (8, 12, 26, 52)


# --------------------------------------------------------------------------- crypto
def _derive(secret, salt):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITER)
    return kdf.derive(secret.encode())


def _encrypt(key, raw):
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, raw, None)


def _decrypt(key, blob):
    return AESGCM(key).decrypt(blob[:12], blob[12:], None)


def _need(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"Secret {name} ontbreekt")
    return v


# --------------------------------------------------------------------------- state
def restore():
    """Cache terugzetten en secrets wegschrijven waar de app ze verwacht."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "rb") as f:
            blob = f.read()
        key = _derive(_need("STATE_KEY"), blob[:16])
        raw = _decrypt(key, blob[16:])
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
            tar.extractall(HERE, filter="data")
        print("Cache teruggezet")
    else:
        print("Geen cache gevonden: eerste run")
    with open(paths.ENV, "w", encoding="utf-8") as f:
        f.write(f"INTERVALS_ATHLETE_ID={os.environ.get('INTERVALS_ATHLETE_ID', '')}\n")
        f.write(f"INTERVALS_API_KEY={os.environ.get('INTERVALS_API_KEY', '')}\n")
    tok = os.path.join(paths.TOKENS, "garmin_tokens.json")
    # Ververste tokens uit de cache gaan voor; het secret is alleen de start
    if not os.path.exists(tok) and os.environ.get("GARMIN_TOKENS"):
        os.makedirs(paths.TOKENS, exist_ok=True)
        with open(tok, "w", encoding="utf-8") as f:
            f.write(os.environ["GARMIN_TOKENS"])


def save():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for item in STATE_ITEMS:
            p = os.path.join(HERE, item)
            if os.path.exists(p):
                tar.add(p, arcname=item)
    salt = os.urandom(16)
    blob = salt + _encrypt(_derive(_need("STATE_KEY"), salt), buf.getvalue())
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "wb") as f:
        f.write(blob)
    print(f"Cache opgeslagen ({len(blob) // 1024} KB)")


# --------------------------------------------------------------------------- acties vanaf de website
def action(name, args_json):
    import app
    args = json.loads(args_json or "{}")
    fn = {"goal": app.save_goal, "settings": app.save_settings, "push_workout": app.push_workout,
          "unpush_workout": app.unpush_workout, "garmin_zones": app.set_garmin_zones}.get(name)
    if name in ("", "sync"):
        return
    if not fn:
        sys.exit(f"Onbekende actie: {name}")
    print(f"Actie {name}: {fn(args)}")


# --------------------------------------------------------------------------- statische site
def build(out):
    import app
    import metrics as M
    import store

    pw = _need("DASHBOARD_PASSWORD")
    # Vast zout per repository: zo blijft de afgeleide sleutel gelijk tussen builds ("onthouden op dit apparaat")
    salt = hashlib.sha256(f"hs-dashboard:{os.environ.get('GITHUB_REPOSITORY', 'lokaal')}".encode()).digest()[:16]
    key = _derive(pw, salt)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "data"))

    def put(name, obj):
        raw = json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":")).encode()
        with open(os.path.join(out, "data", name), "wb") as f:
            f.write(_encrypt(key, raw))

    base = None
    for weeks in PERIODS:
        p = app.build_payload(weeks)
        put(f"dash-{weeks}.enc", p)
        base = base or p
    # Scenario-schuif: alleen de scenario-sectie verschilt per km/week
    put("scenarios.enc", {km: app.build_payload(12, km)["training"]["scenario"] for km in KM_STEPS})
    # Streams/splits per run voor het detailpaneel (laatste 120 dagen)
    cutoff = (dt.date.today() - dt.timedelta(days=120)).isoformat()
    put("runs.enc", {a["id"]: M.run_detail(a["id"]) for a in base["activities"] if a["date"] >= cutoff})

    meta = {"built_at": dt.datetime.now().isoformat(timespec="seconds"), "salt": base64.b64encode(salt).decode(),
            "iterations": PBKDF2_ITER, "periods": PERIODS, "km_steps": list(KM_STEPS),
            "repo": os.environ.get("GITHUB_REPOSITORY", ""), "workflow": "dashboard.yml"}
    with open(os.path.join(out, "data", "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    with open(os.path.join(HERE, "static", "index.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace("<script>\n// ===================================================================== utils",
                        "<script>window.HS_STATIC = true;</script>\n<script>\n// ===================================================================== utils", 1)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(out, ".nojekyll"), "w") as f:
        f.write("")
    store_meta = store.load()["meta"]
    print(f"Site gebouwd in {out} (sync {store_meta.get('synced_at')})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "restore":
        restore()
    elif cmd == "save":
        save()
    elif cmd == "sync":
        import store
        print(store.sync())
    elif cmd == "action":
        action(sys.argv[2] if len(sys.argv) > 2 else "", sys.argv[3] if len(sys.argv) > 3 else "{}")
    elif cmd == "build":
        build(sys.argv[2] if len(sys.argv) > 2 else "site")
    else:
        sys.exit(__doc__)
