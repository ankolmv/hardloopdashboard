"""Minimale client voor de intervals.icu API (alleen standaardbibliotheek).

Authenticatie: HTTP Basic met gebruikersnaam "API_KEY" en je API-sleutel als wachtwoord.
De sleutel en het athlete-ID worden gelezen uit het bestand .env in deze map.
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://intervals.icu/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_env(path=None):
    import paths
    path = path or paths.ENV
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class IntervalsError(Exception):
    pass


class IntervalsClient:
    def __init__(self, athlete_id=None, api_key=None):
        env = load_env()
        self.athlete_id = athlete_id or env.get("INTERVALS_ATHLETE_ID") or os.environ.get("INTERVALS_ATHLETE_ID")
        api_key = api_key or env.get("INTERVALS_API_KEY") or os.environ.get("INTERVALS_API_KEY")
        if not self.athlete_id or not api_key:
            raise IntervalsError(
                "INTERVALS_ATHLETE_ID en/of INTERVALS_API_KEY ontbreken. Vul het bestand .env in."
            )
        token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
        self._auth = f"Basic {token}"

    def _request(self, method, path, params=None, body=None):
        url = f"{BASE_URL}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._auth)
        req.add_header("Accept", "application/json")
        # Cloudflare blokkeert de standaard "Python-urllib" user-agent (error 1010)
        req.add_header("User-Agent", "Hardloopschema/1.0 (+https://intervals.icu/api)")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise IntervalsError(f"intervals.icu {method} {path} gaf HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise IntervalsError(f"Kan intervals.icu niet bereiken: {e.reason}") from e

    # --- Lezen ---------------------------------------------------------------
    def athlete(self):
        return self._request("GET", f"/athlete/{self.athlete_id}")

    def wellness(self, oldest, newest):
        return self._request("GET", f"/athlete/{self.athlete_id}/wellness",
                             {"oldest": oldest, "newest": newest}) or []

    def activities(self, oldest, newest):
        return self._request("GET", f"/athlete/{self.athlete_id}/activities",
                             {"oldest": oldest, "newest": newest}) or []

    def events(self, oldest, newest, category="WORKOUT"):
        params = {"oldest": oldest, "newest": newest}
        if category:
            params["category"] = category
        return self._request("GET", f"/athlete/{self.athlete_id}/events", params) or []

    def activity_streams(self, activity_id, types="time,distance,heartrate,velocity_smooth,altitude,watts,cadence,latlng"):
        """Lijst van {"type": ..., "data": [...]} per stream."""
        return self._request("GET", f"/activity/{activity_id}/streams.json", {"types": types}) or []

    # --- Schrijven -----------------------------------------------------------
    def upsert_events(self, events):
        """Maakt events aan of werkt ze bij op basis van external_id."""
        return self._request("POST", f"/athlete/{self.athlete_id}/events/bulk",
                             {"upsert": "true"}, events)

    def delete_event(self, event_id):
        return self._request("DELETE", f"/athlete/{self.athlete_id}/events/{event_id}")


def threshold_pace_ms(athlete):
    """Drempeltempo voor hardlopen in m/s uit de sportinstellingen, of None."""
    for s in (athlete or {}).get("sportSettings", []) or []:
        if "Run" in (s.get("types") or []):
            tp = s.get("threshold_pace")
            if tp:
                tp = float(tp)
                # intervals.icu slaat dit op in m/s; vang een eventuele s/km-waarde af
                return 1000.0 / tp if tp > 20 else tp
    return None
