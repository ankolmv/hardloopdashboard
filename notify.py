"""Meldingen via ntfy (https://ntfy.sh): ochtendbericht, analyse na een run, wekelijkse terugblik en storingen.

Na elke sync aangeroepen (`python cloud.py notify`). Een logboek in data/notify.json voorkomt dubbele berichten.
Zonder NTFY_TOPIC (omgeving of .env) wordt er niets verstuurd.

Lokaal testen:  python notify.py test          (stuurt een testbericht)
                python notify.py dry           (laat zien wat er nu verstuurd zou worden, zonder te versturen)
"""
import datetime as dt
import json
import os
import sys
import urllib.request

import paths

LOG_PATH = os.path.join(paths.DATA, "notify.json")
REVIEWS_PATH = os.path.join(paths.DATA, "reviews.json")
UA = {"User-Agent": "hardloopdashboard/1.0"}
COMPASS = ["N", "NO", "O", "ZO", "Z", "ZW", "W", "NW"]


# --------------------------------------------------------------------------- basis
def _topic():
    t = os.environ.get("NTFY_TOPIC")
    if t:
        return t.strip()
    try:
        from intervals_client import load_env
        return (load_env().get("NTFY_TOPIC") or "").strip() or None
    except Exception:
        return None


def dashboard_url():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"
    return "http://localhost:8765/"


def send(title, message, tags=(), priority=3, click=None, dry=False):
    """Eén bericht naar ntfy (JSON, zodat UTF-8 in titel en tekst goed gaat)."""
    topic = _topic()
    if dry or not topic:
        print(f"[{'dry' if dry else 'geen NTFY_TOPIC'}] {title}\n{message}\n")
        return False
    body = json.dumps({"topic": topic, "title": title, "message": message, "tags": list(tags),
                       "priority": priority, "click": click or dashboard_url()}).encode()
    req = urllib.request.Request("https://ntfy.sh/", data=body, headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()
    print(f"Melding verstuurd: {title}")
    return True


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def load_reviews():
    return _load(REVIEWS_PATH, [])


def _fmt(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",") if x is not None else "–"


def _steps_txt(steps):
    """Korte samenvatting van de doelen: '123–146 bpm' of '4:12–4:22/km'."""
    out = []
    for s in steps:
        for s2 in ([s] if s["kind"] != "repeat" else s["steps"]):
            if s2.get("pace_txt") and s2["kind"] == "interval":
                out.append(f"{s['n']}× " if s["kind"] == "repeat" else "")
                out[-1] += f"{round(s2['secs'] / 60, 1):g} min op {s2['pace_txt']}/km".replace(".", ",")
            elif s2.get("hr") and s2["kind"] == "run":
                out.append(f"{round(s2['secs'] / 60)} min op {s2['hr'][0]}–{s2['hr'][1]} bpm")
    return "; ".join(dict.fromkeys(out))


# --------------------------------------------------------------------------- weer
def weather(home, day):
    """Weer overdag (7–19 u) op je startpunt: temperatuur, regenkans, wind."""
    if not home:
        return None
    url = ("https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}&hourly=temperature_2m,precipitation_probability,"
           "wind_speed_10m,wind_direction_10m&timezone=Europe%2FAmsterdam&start_date={d}&end_date={d}").format(home[0], home[1], d=day)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            h = json.load(r)["hourly"]
    except Exception as e:
        print(f"Weer niet opgehaald: {e}")
        return None
    idx = [i for i, t in enumerate(h["time"]) if 7 <= int(t[11:13]) <= 19]
    if not idx:
        return None
    temps = [h["temperature_2m"][i] for i in idx]
    rain = max(h["precipitation_probability"][i] or 0 for i in idx)
    wind = sum(h["wind_speed_10m"][i] for i in idx) / len(idx)
    mid = idx[len(idx) // 2]
    direction = COMPASS[round(h["wind_direction_10m"][mid] / 45) % 8]
    bft = next(b for b, lim in enumerate((1, 6, 12, 20, 29, 39, 50, 62, 75, 89, 103, 118, 999)) if wind < lim)
    return f"{round(min(temps))}–{round(max(temps))} °C, regenkans {rain}%, wind {direction} {bft} Bft"


# --------------------------------------------------------------------------- berichten
def morning_msg(p, today):
    sg = p["overview"].get("suggestion") or {}
    rec = (p.get("recovery") or {}).get("days") or []
    r = rec[-1] if rec and rec[-1]["date"] == today.isoformat() else {}
    lines = []
    if sg:
        when = "" if sg.get("for_today", True) else f" (voor {sg['weekday']})"
        head = sg["title"] + (f" · {sg['minutes']} min · ±{_fmt(sg.get('est_km'))} km" if sg.get("minutes") else "")
        lines.append(f"🏃 {head}{when}")
        doel = _steps_txt(sg.get("steps") or [])
        if doel:
            lines.append(f"   {doel}")
        adj = [w for w in sg.get("why", []) if w.startswith(("Aangepast", "Je herstel is", "Readiness is matig"))]
        if adj:
            lines.append(f"   {adj[0]}")
    herstel = []
    if r.get("readiness") is not None:
        herstel.append(f"Readiness {r['readiness']}")
    if r.get("sleep_h"):
        herstel.append(f"slaap {_fmt(r['sleep_h'])} u")
    if r.get("hrv_status"):
        herstel.append(f"HRV {r['hrv_status'].lower().replace('_', ' ')}")
    if r.get("bb_now") is not None:
        herstel.append(f"Body Battery {r['bb_now']}")
    if herstel:
        lines.append("💤 " + ", ".join(herstel))
    w = weather((p.get("route") or {}).get("home"), today.isoformat())
    if w:
        lines.append(f"🌤 {w}")
    g, pl = p.get("goal") or {}, p.get("plan") or {}
    tw = pl.get("this_week") or {}
    doel = []
    if g.get("proj"):
        now_pred = g["proj"].get(0) or g["proj"].get("0")
        doel.append(f"{_fmt(g['distance_km'], 0 if g['distance_km'] % 1 == 0 else 1)} km nu {now_pred['time']} (doel {g['time']})")
    elif g.get("pred"):
        doel.append(f"{_fmt(g['distance_km'], 0 if g['distance_km'] % 1 == 0 else 1)} km nu {g['pred']}")
    if g.get("days_to") is not None:
        doel.append(f"nog {g['days_to']} dagen")
    if tw:
        ran = sum((d.get("actual") or {}).get("km", 0) for d in tw.get("days", []))
        doel.append(f"week {_fmt(ran)} van ±{round(tw['target_km'])} km")
    if doel:
        lines.append("🎯 " + " · ".join(doel))
    return "Goedemorgen! " + (sg.get("title", "") if sg else ""), "\n".join(lines)


def run_msg(p):
    L = p["overview"].get("last_session")
    if not L:
        return None
    tips = [t for t in L.get("tips", []) if t.get("tone") == "warn"] + L.get("good", []) + L.get("tips", [])
    lines = [f"{L['type_label']} · {_fmt(L['km'])} km · {L['pace']}/km" + (f" · gem. {L['avg_hr']} bpm" if L.get("avg_hr") else ""),
             f"Oordeel: {L['verdict']}"]
    if tips:
        lines.append(tips[0]["text"])
    return f"✓ {L['name']}", "\n".join(lines)


def weekly_review(p, today):
    pl = p.get("plan") or {}
    w, nw = pl.get("this_week") or {}, pl.get("next_week") or {}
    if not w:
        return None
    days = w.get("days", [])
    km = sum((d.get("actual") or {}).get("km", 0) for d in days)
    done = [d for d in days if d.get("status") in ("done", "extra")]
    missed = [d for d in days if d.get("status") == "missed"]
    hard = [d for d in done if d.get("hard") or d["kind"] in ("drempel", "interval", "wedstrijdtempo")]
    longrun = any(d["kind"] == "lang" for d in done)
    spark = (p["overview"]["kpis"]["vdot"].get("spark") or [])
    vd = [v for v in spark if v is not None]
    rec = (p.get("recovery") or {}).get("days") or []
    ws = dt.date.fromisoformat(w["start"])
    rd_this = [r["readiness"] for r in rec if r.get("readiness") is not None and ws.isoformat() <= r["date"]]
    rd_prev = [r["readiness"] for r in rec if r.get("readiness") is not None
               and (ws - dt.timedelta(days=7)).isoformat() <= r["date"] < ws.isoformat()]
    pct = round(km / w["target_km"] * 100) if w.get("target_km") else None
    lines = [f"{_fmt(km)} km van ±{round(w['target_km'])} km ({pct}%)" if pct is not None else f"{_fmt(km)} km",
             f"{len(done)} trainingen, waarvan {len(hard)} zwaar" + (", lange duurloop ✓" if longrun else ", geen lange duurloop")
             + (f"; gemist: {', '.join(d['weekday'] for d in missed)}" if missed else "")]
    if len(vd) >= 2:
        diff = vd[-1] - vd[-2]
        lines.append(f"VDOT {_fmt(vd[-1])} ({'+' if diff >= 0 else ''}{_fmt(diff)} t.o.v. vorige week)")
    if rd_this:
        a = sum(rd_this) / len(rd_this)
        lines.append(f"Gem. Readiness {round(a)}" + (f" (vorige week {round(sum(rd_prev) / len(rd_prev))})" if rd_prev else ""))
    good = []
    if pct is not None and 85 <= pct <= 115:
        good.append("omvang precies volgens plan")
    elif pct is not None and pct > 115:
        good.append("flink meer gelopen dan gepland: let op je herstel")
    elif pct is not None:
        good.append("minder gelopen dan gepland: volgende week rustig opbouwen, niet inhalen")
    if longrun:
        good.append("lange duurloop gedaan")
    lines.append("→ " + "; ".join(good) + ".")
    if nw:
        lines.append(f"Volgende week ({nw['label']}): {nw['phase_label'].lower()}, ±{round(nw['target_km'])} km, "
                     f"{nw['sessions']} trainingen waarvan {nw['quality']} kwaliteit.")
    return {"week": w["start"], "label": w["label"], "range": w["range"], "created": today.isoformat(),
            "title": f"Terugblik {w['label']}", "lines": lines, "km": round(km, 1), "target_km": w.get("target_km"),
            "sessions": len(done), "quality": len(hard)}


def token_expiry():
    """Vervaldatum van de GitHub-token voor de knoppen (fine-grained tokens geven die mee in een header)."""
    tok, repo = os.environ.get("ACTIONS_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (tok and repo):
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}",
                                 headers={**UA, "Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            exp = r.headers.get("github-authentication-token-expiration")
    except urllib.error.HTTPError as e:
        return "invalid" if e.code in (401, 403) else None
    except Exception:
        return None
    return dt.date.fromisoformat(exp[:10]) if exp else None


# --------------------------------------------------------------------------- hoofdingang
def run(p, now=None, dry=False):
    now = now or dt.datetime.now()
    today = now.date()
    log = _load(LOG_PATH, {})
    sent = []

    def out(title, msg, **kw):
        send(title, msg, dry=dry, **kw)
        sent.append(title)

    # ---- ochtend: zodra de Readiness van vandaag er is, uiterlijk 9:00
    rec = (p.get("recovery") or {}).get("days") or []
    measured = bool(rec and rec[-1]["date"] == today.isoformat() and rec[-1].get("readiness") is not None)
    if log.get("morning") != today.isoformat() and 5 <= now.hour < 11 and (measured or now.hour >= 9):
        title, msg = morning_msg(p, today)
        out(title, msg, tags=["sunrise"])
        log["morning"] = today.isoformat()

    # ---- nieuwe run geanalyseerd
    L = p["overview"].get("last_session")
    if L:
        if "last_run" not in log:
            log["last_run"] = L["id"]  # eerste keer: alleen onthouden
        elif L["id"] != log["last_run"]:
            if L["date"] >= (today - dt.timedelta(days=1)).isoformat():
                m = run_msg(p)
                if m:
                    out(*m, tags=["runner"])
            log["last_run"] = L["id"]

    # ---- wekelijkse terugblik: zondag vanaf 20:00
    ws = (today - dt.timedelta(days=today.weekday())).isoformat()
    if today.weekday() == 6 and now.hour >= 20 and log.get("week") != ws:
        rv = weekly_review(p, today)
        if rv:
            reviews = [r for r in load_reviews() if r["week"] != rv["week"]] + [rv]
            if not dry:
                _save(REVIEWS_PATH, reviews[-26:])
            out(rv["title"], "\n".join(rv["lines"]), tags=["bar_chart"])
        log["week"] = ws

    # ---- storingen (max. 1 melding per soort per dag)
    fails = log.setdefault("fail", {})

    def fail(kind, title, msg):
        if fails.get(kind) != today.isoformat():
            out(title, msg, tags=["warning"], priority=4)
            fails[kind] = today.isoformat()

    g = (p.get("meta") or {}).get("garmin")
    log["garmin_bad"] = (log.get("garmin_bad", 0) + 1) if (p.get("garmin_linked") and g and g != "ok") else 0
    if log["garmin_bad"] >= 2:
        fail("garmin", "Garmin-koppeling werkt niet",
             f"Garmin gaf een fout ({g}). Readiness, slaap en pushes naar je horloge werken niet. "
             "Oplossing: draai op je pc 'python garmin_login.py' en daarna set_secrets.ps1.")
    if log.get("token_checked") != today.isoformat():
        exp = token_expiry()
        log["token_checked"] = today.isoformat()
        if exp == "invalid":
            fail("token", "GitHub-token werkt niet meer",
                 "De knoppen op de site (opslaan, synchroniseren, naar Garmin) werken niet. Maak een nieuwe token en draai set_actions_token.ps1.")
        elif isinstance(exp, dt.date):
            left = (exp - today).days
            if left in (14, 7, 3, 1, 0) or left < 0:
                fail("token", f"GitHub-token verloopt {'vandaag' if left == 0 else 'is verlopen' if left < 0 else f'over {left} dagen'}",
                     f"Vervaldatum {exp.isoformat()}. Maak op github.com een nieuwe fine-grained token (Actions: read and write "
                     "op deze repository) en draai set_actions_token.ps1, anders werken de knoppen op de site niet meer.")

    if not dry:
        _save(LOG_PATH, log)
    return sent


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "test":
        ok = send("Test van je hardloopdashboard", "Als je dit ziet, werken de meldingen. 🏃", tags=["white_check_mark"])
        print("Verstuurd." if ok else "Niet verstuurd: zet eerst NTFY_TOPIC (set_ntfy.ps1).")
    elif cmd == "dry":
        import app
        when = dt.datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else None
        p = app.build_payload()
        print(run(p, when, dry=True) or "Nu niets te versturen.")
    else:
        sys.exit(__doc__)
