"""Officiële Strava-API: populaire hardloopsegmenten rond je startpunt.

Tokens staan in .strava_tokens/tokens.json (aanmaken met: python strava_login.py).
Strava ververst het refresh-token soms; de nieuwe waarde wordt direct weer opgeslagen.
"""
import json
import math
import os
import time
import urllib.parse
import urllib.request

import paths

TOKENS_DIR = os.path.join(paths.BASE, ".strava_tokens")
TOKENS = os.path.join(TOKENS_DIR, "tokens.json")
API = "https://www.strava.com/api/v3"


def available():
    return os.path.exists(TOKENS)


def _load():
    with open(TOKENS, encoding="utf-8") as f:
        return json.load(f)


def _save(t):
    os.makedirs(TOKENS_DIR, exist_ok=True)
    with open(TOKENS, "w", encoding="utf-8") as f:
        json.dump(t, f)


def _post(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def exchange_code(client_id, client_secret, code):
    t = _post("https://www.strava.com/oauth/token", {"client_id": client_id, "client_secret": client_secret,
                                                     "code": code, "grant_type": "authorization_code"})
    tok = {"client_id": client_id, "client_secret": client_secret, "refresh_token": t["refresh_token"],
           "access_token": t["access_token"], "expires_at": t["expires_at"]}
    _save(tok)
    return tok


def access_token():
    t = _load()
    if t.get("access_token") and t.get("expires_at", 0) > time.time() + 120:
        return t["access_token"]
    r = _post("https://www.strava.com/oauth/token", {"client_id": t["client_id"], "client_secret": t["client_secret"],
                                                     "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
    t.update(access_token=r["access_token"], refresh_token=r["refresh_token"], expires_at=r["expires_at"])
    _save(t)
    return t["access_token"]


def _get(path, params):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token()}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def decode_polyline(s):
    """Google encoded polyline -> [[lat, lon], ...]."""
    pts, i, lat, lon = [], 0, 0, 0
    while i < len(s):
        for k in (0, 1):
            shift = res = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                res |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(res >> 1) if res & 1 else res >> 1
            if k == 0:
                lat += d
            else:
                lon += d
        pts.append([lat / 1e5, lon / 1e5])
    return pts


def explore_around(center, radius_km=7, grid=3):
    """Populaire hardloopsegmenten in een raster van grid×grid vakken rond center.

    Strava geeft per vak de (max) 10 populairste segmenten; volgorde = populariteit.
    """
    lat0, lon0 = center
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * math.cos(math.radians(lat0)))
    seen, out = set(), []
    for gy in range(grid):
        for gx in range(grid):
            sw = (lat0 - dlat + 2 * dlat * gy / grid, lon0 - dlon + 2 * dlon * gx / grid)
            ne = (sw[0] + 2 * dlat / grid, sw[1] + 2 * dlon / grid)
            j = _get("/segments/explore", {"bounds": f"{sw[0]:.5f},{sw[1]:.5f},{ne[0]:.5f},{ne[1]:.5f}",
                                           "activity_type": "running"})
            for rank, sg in enumerate(j.get("segments") or []):
                if sg["id"] in seen:
                    continue
                seen.add(sg["id"])
                pts = decode_polyline(sg.get("points") or "")
                if len(pts) > 60:  # vereenvoudigen voor de kaart en het rekenwerk
                    step = len(pts) / 60
                    pts = [pts[int(k * step)] for k in range(60)] + [pts[-1]]
                out.append({"id": sg["id"], "name": sg.get("name"), "rank": rank, "distance": sg.get("distance"),
                            "pts": [[round(a, 5), round(b, 5)] for a, b in pts]})
    return out
