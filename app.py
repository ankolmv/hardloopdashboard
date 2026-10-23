"""Lokale server voor het prestatiedashboard (hardlopen).

Start met:  python app.py   (of dubbelklik start_dashboard.bat)
Open daarna http://localhost:8765

Alle data voor het dashboard komt uit build_payload(); dat maakt het later eenvoudig om er
een statische (versleutelde) build van te maken voor hosting.
"""
import datetime as dt
import json
import os
import statistics
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import analysis
import garmin_client
import insights
import metrics as M
import plan as PL
import projection as P
import store
from intervals_client import IntervalsError, load_env

PORT = int(os.environ.get("HS_PORT", "8765"))
HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
import paths  # noqa: E402

GOAL_PATH = paths.GOAL


# --------------------------------------------------------------------------- doel
def parse_time(s):
    try:
        parts = [float(p) for p in str(s).strip().split(":") if p != ""]
    except ValueError:
        return None
    if not parts:
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs if len(parts) > 1 else parts[0] * 60


def fmt_time(s):
    if s is None:
        return None
    s = int(round(s))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


SETTINGS_PATH = os.path.join(paths.BASE, "settings.json")


def load_settings():
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return {"hr_zones": "model", "long_days": [4, 5, 6], **json.load(f)}
    return {"hr_zones": "model", "long_days": [4, 5, 6]}


def save_settings(body):
    s = load_settings()
    if body.get("hr_zones") in ("model", "garmin"):
        s["hr_zones"] = body["hr_zones"]
    if isinstance(body.get("long_days"), list):
        s["long_days"] = sorted({int(d) for d in body["long_days"] if 0 <= int(d) <= 6})
    if body.get("week"):  # trainingsdagen voor één week (null = terug naar je vaste dagen)
        try:
            ws = M.week_start(dt.date.fromisoformat(str(body["week"])))
        except ValueError:
            raise ValueError("Ongeldige week.")
        this_ws = M.week_start(dt.date.today())
        wd = {k: v for k, v in (s.get("week_days") or {}).items() if k >= this_ws.isoformat()}  # oude weken opruimen
        if isinstance(body.get("run_days"), list):
            days = sorted({int(d) for d in body["run_days"] if 0 <= int(d) <= 6})
            if not days:
                raise ValueError("Kies minstens 1 trainingsdag.")
            wd[ws.isoformat()] = days
        else:
            wd.pop(ws.isoformat(), None)
        s["week_days"] = wd
    elif isinstance(body.get("run_days"), list):  # vaste trainingsdagen (0 = maandag)
        days = sorted({int(d) for d in body["run_days"] if 0 <= int(d) <= 6})
        if not 2 <= len(days) <= 7:
            raise ValueError("Kies minstens 2 trainingsdagen.")
        s["run_days"] = days
    if "home" in body:  # startpunt voor routes: [lat, lon]
        h = body["home"]
        try:
            lat, lon = float(h[0]), float(h[1])
        except (TypeError, ValueError, IndexError):
            raise ValueError("Startpunt moet twee getallen zijn: breedtegraad en lengtegraad, bijv. 52.2, 4.9.")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Startpunt ligt buiten het geldige bereik.")
        s["home"] = [round(lat, 6), round(lon, 6)]
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    return s


PUSHED_PATH = os.path.join(paths.DATA, "pushed.json")
ZONES_BACKUP_PATH = os.path.join(paths.DATA, "hr_zones_backup.json")


def load_pushed():
    if os.path.exists(PUSHED_PATH):
        with open(PUSHED_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def push_workout(body):
    """Zet de suggestie (of een geplande dag uit het trainingsplan) voor `date` als workout in Garmin Connect.

    De server berekent alles zelf opnieuw; een eerdere dashboard-workout op die datum wordt vervangen.
    """
    p = build_payload()
    sug = p["overview"]["suggestion"]
    if not sug or sug["date"] != body.get("date"):
        day = PL.planned_for(p.get("plan"), body.get("date"))
        if not day or day["date"] < p["today"] or day.get("status") in ("done", "extra"):
            raise ValueError("Deze training is intussen veranderd. Ververs het dashboard en probeer opnieuw.")
        sug = {"date": day["date"], "title": day["title"], "steps": day["steps"], "why": [w for w in day["why"] if w]}
    if not sug["steps"]:
        raise ValueError("Voor een rustdag is er geen training om op je Garmin te zetten.")
    g = garmin_client.connect()
    pushed = load_pushed()
    old = pushed.get(sug["date"])
    if old and old.get("workoutId"):
        garmin_client._try(g.delete_workout, old["workoutId"])
    res = g.upload_running_workout(analysis.to_garmin_workout(sug))
    wid = res.get("workoutId") if isinstance(res, dict) else None
    if not wid:
        raise ValueError(f"Garmin gaf geen workout-ID terug: {str(res)[:200]}")
    g.schedule_workout(wid, sug["date"])
    pushed[sug["date"]] = {"workoutId": wid, "title": sug["title"],
                           "at": dt.datetime.now().isoformat(timespec="seconds")}
    _write_json(PUSHED_PATH, pushed)
    return {"ok": True, "workoutId": wid, "date": sug["date"], "title": sug["title"]}


def unpush_workout(body):
    pushed = load_pushed()
    old = pushed.pop(body.get("date"), None)
    if old and old.get("workoutId"):
        g = garmin_client.connect()
        g.delete_workout(old["workoutId"])
    _write_json(PUSHED_PATH, pushed)
    return {"ok": True}


def _running_zone_obj(zones):
    run = next((z for z in zones if z.get("sport") == "RUNNING"), None)
    if run:
        return dict(run)
    base = next((z for z in zones if z.get("sport") == "DEFAULT"), zones[0])
    return {**base, "sport": "RUNNING"}


def garmin_watch_status(ctx, model_rows):
    """Wijken de zones op het horloge af van de model-zones?"""
    if not model_rows or not ctx.get("hr_floors"):
        return None
    watch = ctx["hr_floors"]
    model = [watch[0]] + [r["from"] for r in model_rows[1:]]
    sports = ctx.get("hr_zones_all") or {"RUNNING": watch}
    off = [s for s, fl in sports.items() if not all(abs(a - b) <= 1 for a, b in zip(fl[1:], model[1:]))]
    return {"watch": watch, "model": model, "in_sync": not off, "off_sports": off, "sports": sports,
            "backup": os.path.exists(ZONES_BACKUP_PATH)}


def set_garmin_zones(body):
    """Model-zones op Garmin zetten voor alle sporten (of de originele zones terugzetten)."""
    g = garmin_client.connect()
    current = g.get_heart_rate_zones_v2()
    if not isinstance(current, list) or not current:
        raise ValueError("Kon de huidige Garmin-zones niet lezen.")
    if body.get("restore"):
        if not os.path.exists(ZONES_BACKUP_PATH):
            raise ValueError("Er is geen backup van je originele Garmin-zones.")
        with open(ZONES_BACKUP_PATH, encoding="utf-8") as f:
            backup = json.load(f)
        restore = [{**z, "changeState": "CHANGED"} for z in backup]
        base = next((z for z in backup if z.get("sport") == "DEFAULT"), backup[0])
        # Sporten die het dashboard heeft toegevoegd (niet in de backup) terug naar de standaardwaarden
        for z in current:
            if z.get("sport") not in {b.get("sport") for b in backup}:
                restore.append({**base, "sport": z.get("sport"), "changeState": "CHANGED"})
        g.update_heart_rate_zones(restore)
        os.remove(ZONES_BACKUP_PATH)
    else:
        p = build_payload()
        rows = (p["zones"].get("hr_zones_by") or {}).get("model")
        if not rows:
            raise ValueError("Model-zones zijn nog niet beschikbaar.")
        if not os.path.exists(ZONES_BACKUP_PATH):
            _write_json(ZONES_BACKUP_PATH, current)
        objs = [dict(z) for z in current]
        if not any(z.get("sport") == "RUNNING" for z in objs):
            objs.append(_running_zone_obj(current))
        for obj in objs:  # alle sporten: standaard, hardlopen, fietsen, ...
            for i, r in enumerate(rows[1:], start=2):
                obj[f"zone{i}Floor"] = r["from"]
            obj["maxHeartRateUsed"] = p["zones"]["max_hr"]
            obj["restingHeartRateUsed"] = p["zones"]["rest_hr"]
            obj["changeState"] = "CHANGED"
        g.update_heart_rate_zones(objs)
    after = g.get_heart_rate_zones_v2()
    store.sync()  # nieuwe zones in de cache
    return {"ok": True, "zones": {z.get("sport"): [z.get(f"zone{i}Floor") for i in range(1, 6)] for z in after}}


def load_goal():
    if os.path.exists(GOAL_PATH):
        with open(GOAL_PATH, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_goal(body):
    """Doel: een evenement (met datum) of algemeen (bijv. 'snellere 10 km'); de doeltijd is optioneel."""
    try:
        km = float(str(body.get("distance_km")).replace(",", "."))
    except ValueError:
        km = 0
    if not 1.5 <= km <= 100:
        raise ValueError("Geef een afstand tussen 1,5 en 100 km.")
    goal = {"type": "event" if body.get("type") == "event" else "general", "distance_km": km}
    if str(body.get("time") or "").strip():
        secs = parse_time(body.get("time"))
        if not secs:
            raise ValueError("Geef de doeltijd zoals 45:00 of 1:45:00 (of laat hem leeg).")
        goal["time"] = fmt_time(secs)
    if goal["type"] == "event":
        try:
            date = dt.date.fromisoformat(str(body.get("date")))
        except ValueError:
            raise ValueError("Geef de datum van het evenement.")
        if date < dt.date.today():
            raise ValueError("De datum van het evenement ligt in het verleden.")
        goal["date"] = date.isoformat()
    name = str(body.get("name") or "").strip()[:60]
    if name:
        goal["name"] = name
    old = load_goal() or {}
    with open(GOAL_PATH, "w", encoding="utf-8") as f:
        json.dump(goal, f, indent=2)
    if (old.get("distance_km"), old.get("type"), old.get("date")) != (goal["distance_km"], goal["type"], goal.get("date")):
        s = load_settings()  # nieuw doel: de 4-weekse cyclus begint deze week
        s["plan_start"] = M.week_start(dt.date.today()).isoformat()
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    return goal


# --------------------------------------------------------------------------- helpers
def last(rows, key):
    return next((r[key] for r in reversed(rows) if r.get(key) is not None), None)


def weekly_from_daily(daily, key, weeks, agg=statistics.mean):
    """Daggegevens samenvatten per week (voor sparklines en weekgrafieken)."""
    by = {}
    for d in daily:
        if d.get(key) is None:
            continue
        ws = M.week_start(dt.date.fromisoformat(d["date"])).isoformat()
        by.setdefault(ws, []).append(d[key])
    return [round(agg(by[w["week"]]), 2) if w["week"] in by else None for w in weeks]


def sel(rows, keys):
    return [{k: r.get(k) for k in keys} for r in rows]


# --------------------------------------------------------------------------- payload
def build_payload(period_weeks=12, km_override=None, hr_zones=None):
    data = store.load()
    if not data:
        store.sync()
        data = store.load()
    today = dt.date.today()
    A = M.build(data)
    runs, all_weeks, daily, ctx = A["runs"], A["run_weeks"], A["daily"], A["ctx"]
    snaps = data.get("garmin_snapshots") or []
    snap = snaps[-1] if snaps else {}

    best_recent = P.recent_best(runs, today)
    tr = P.trend([{**w, "n": w["runs"]} for w in all_weeks], today,
                 anchor=best_recent["value"] if best_recent else None)
    settings = load_settings()
    if hr_zones in ("model", "garmin"):  # weergavekeuze zonder de opgeslagen instelling te wijzigen
        settings = {**settings, "hr_zones": hr_zones}
    garmin_floors = ctx.get("hr_floors")
    model_floors = M.model_hr_floors(tr["now"], ctx["rest_hr"], ctx["max_hr"]) if tr else None
    use_model = settings["hr_zones"] == "model" and model_floors
    active_floors = model_floors if use_model else garmin_floors
    if use_model:
        for r in runs:
            s = store.streams(r["id"])
            if s.get("heartrate") and s.get("time"):
                r["zones"] = M.hr_zone_seconds(s["heartrate"], s["time"], active_floors)
        all_weeks = M.weekly_runs(runs, A["calibration"]["offset"], "model")
    data_weeks = sum(1 for w in all_weeks if w["runs"])
    n_hard = sum(1 for r in runs if r["vdot_race"])
    rel, rel_text = P.reliability(data_weeks, n_hard)
    avg_km = statistics.mean(w["km"] for w in all_weeks[-4:]) if all_weeks else 0
    longest = max([w["longest"] or 0 for w in all_weeks[-6:]] or [0])

    start = (M.week_start(today) - dt.timedelta(weeks=period_weeks - 1)).isoformat()
    weeks = [w for w in all_weeks if w["week"] >= start]
    days = [d for d in daily if d["date"] >= start]
    wl = [{"week": w["week"], "label": w["label"], "range": w["range"]} for w in weeks]

    # Tempo bij vaste hartslag
    rest, mx = ctx["rest_hr"], ctx["max_hr"]
    hr_ref = int(round(rest + 0.65 * (mx - rest)))
    hrr_ref = (hr_ref - rest) / (mx - rest)
    by_w = {}
    for r in runs:
        if r["vdot_hr"]:
            v = M.speed_for_vo2(hrr_ref * (r["vdot_hr"] - 3.5) + 3.5)
            by_w.setdefault(M.week_start(dt.date.fromisoformat(r["date"])).isoformat(), []).append(60000 / v)
    pace_ref = [{"week": w["week"], "pace": round(statistics.median(by_w[w["week"]]), 1) if w["week"] in by_w else None}
                for w in weeks]

    # ---------------- Prestaties
    perf = {"reliability": {"level": rel, "text": rel_text, "weeks": data_weeks, "hard_efforts": n_hard,
                            "calibration": A["calibration"]}}
    model_now = {}
    if tr:
        band0 = tr["at"](0)[1]
        preds = {0: P.predictions(tr["now"], band0, avg_km, longest)}
        for h in P.HORIZONS:
            v, b = tr["at"](h)
            preds[h] = P.predictions(v, b, avg_km, longest)
        model_now = {k: preds[0][k]["time"] for k in M.RACE_DISTANCES}
        garmin_race = snap.get("race") or {}
        table = []
        for k in M.RACE_DISTANCES:
            row = {"key": k, "label": M.RACE_LABELS[k], "penalty": preds[0][k]["penalty"],
                   "garmin": fmt_time(garmin_race.get(k)) if garmin_race.get(k) else None}
            for h, p in preds.items():
                row[f"h{h}"] = {"time": fmt_time(p[k]["time"]), "lo": fmt_time(p[k]["lo"]), "hi": fmt_time(p[k]["hi"]),
                                "pace": fmt_time(p[k]["pace"])}
            table.append(row)
        proj = []
        for h in range(0, 13):
            v, b = tr["at"](h)
            ws = M.week_start(today) + dt.timedelta(weeks=h)
            lab, rng = M.week_label(ws)
            proj.append({"week": ws.isoformat(), "label": lab, "range": rng,
                         "v": round(v, 2), "lo": round(v - b, 2), "hi": round(v + b, 2)})
        past = [w for w in all_weeks[:-4] if w.get("vdot")]
        perf.update({
            "vdot": {"now": round(tr["now"], 1), "band": round(band0, 1), "ago4": past[-1]["vdot"] if past else None,
                     "fit_now": round(tr["fit_now"], 1), "anchored": tr["anchored"], "best_recent": best_recent,
                     "slope_month": round(tr["slope"] * 4.35, 2), "raw_slope_month": round(tr["raw_slope"] * 4.35, 2)},
            "predictions": table, "projection": proj, "trend_fit": tr["fit"],
        })
    perf["weeks"] = [{**l, "vdot": w["vdot"], "src": w["vdot_src"]} for l, w in zip(wl, weeks)]
    perf["vo2max_weeks"] = weekly_from_daily(daily, "vo2max", weeks, max)
    perf["vo2max"] = last(daily, "vo2max")
    cutoff = (today - dt.timedelta(days=90)).isoformat()
    best = {}
    for r in runs:
        if r["date"] < cutoff:
            continue
        for D, e in r["efforts"].items():
            if D not in best or e["time"] < best[D]["time"]:
                best[D] = {**e, "date": r["date"], "name": r["name"], "id": r["id"]}
    perf["best_efforts"] = [{"dist": D, "label": "Halve marathon" if D == 21097 else f"{D / 1000:g} km",
                             "time": fmt_time(e["time"]), "pace": fmt_time(e["time"] / (D / 1000)),
                             "vdot": e["vdot"], "hard": e["hard"], "date": e["date"], "name": e["name"], "id": e["id"]}
                            for D, e in sorted(best.items())]
    perf["garmin"] = {k: snap.get(k) for k in ("lt_hr", "lt_pace_s", "endurance", "endurance_class", "hill",
                                               "hill_strength", "hill_endurance")}
    perf["garmin"]["lt_pace"] = fmt_time(snap.get("lt_pace_s")) if snap.get("lt_pace_s") else None
    perf["garmin"]["endurance_hist"] = snap.get("endurance_hist") or []
    perf["garmin_race_hist"] = [{"date": s["date"], **{k: s.get("race", {}).get(k) for k in M.RACE_DISTANCES}}
                                for s in snaps if s.get("race")]

    # ---------------- Doel
    goal = load_goal()
    goal_out = None
    if goal and tr and goal.get("time"):
        D = goal["distance_km"] * 1000
        gs = P.goal_status(D, parse_time(goal["time"]), tr, avg_km, longest, today)
        goal_out = {**goal, **gs, "pace": fmt_time(parse_time(goal["time"]) / goal["distance_km"]),
                    "gap": fmt_time(abs(gs["gap_s"])), "ahead": gs["gap_s"] <= 0,
                    "eta_label": " · ".join(M.week_label(gs["eta_week"])) if gs["eta_week"] else None,
                    "proj": {h: {**p, "time": fmt_time(p["time"]), "lo": fmt_time(p["lo"]), "hi": fmt_time(p["hi"])}
                             for h, p in gs["proj"].items()}}
    elif goal:
        goal_out = {**goal}
        if tr:  # algemeen doel zonder tijd: wat het model nu verwacht
            D = goal["distance_km"] * 1000
            goal_out["pred"] = fmt_time(M.race_time(tr["now"], D) * (1 + P.endurance_penalty(D, avg_km, longest)))
    if goal_out and goal.get("type") == "event" and goal.get("date"):
        goal_out["days_to"] = (dt.date.fromisoformat(goal["date"]) - today).days
        goal_out["weeks_to"] = (M.week_start(dt.date.fromisoformat(goal["date"])) - M.week_start(today)).days // 7

    # ---------------- Training
    km = km_override if km_override is not None else round(avg_km)
    sc = P.scenario(12, runs, daily, all_weeks, km)
    if tr:
        v12 = sc["vdot"][-1] if sc["vdot"] else tr["at"](12)[0]
        long_est = max(longest, min(0.3 * km, 35))
        sc["basis"] = "model" if sc["vdot"] else "trend"
        sc["long_est"] = round(long_est, 1)
        sc["times"] = {k: fmt_time(M.race_time(v12, d) * (1 + P.endurance_penalty(d, km, long_est)))
                       for k, d in M.RACE_DISTANCES.items()}
        if goal:
            Dg = goal["distance_km"] * 1000
            sc["goal_time"] = fmt_time(M.race_time(v12, Dg) * (1 + P.endurance_penalty(Dg, km, long_est)))
    sc["ctl_weeks"] = [{"label": M.week_label(M.week_start(today) + dt.timedelta(weeks=i + 1))[0], "ctl": c}
                       for i, c in enumerate(sc["ctl"])]
    latest_g = next((d for d in reversed(daily) if d.get("training_status") or d.get("load_focus")), {})
    training = {
        "weeks": [{**l, **{k: w[k] for k in ("km", "hours", "runs", "load", "longest", "elev", "trimp", "z_low", "z_mid",
                                                "z_high", "pz_low", "pz_mid", "pz_high", "z7", "pz7", "te_aerobic", "te_anaerobic", "rpe")}}
                  for l, w in zip(wl, weeks)],
        "load": sel([d for d in days if d.get("ctl") is not None], ("date", "ctl", "atl", "tsb", "load_acute", "load_chronic", "acwr")),
        "te_runs": [{"date": r["date"], "name": r["name"], "a": r["te_aerobic"], "an": r["te_anaerobic"], "label": r["te_label"]}
                    for r in runs if r["date"] >= start and r.get("te_aerobic") is not None],
        "rpe_runs": [{"date": r["date"], "name": r["name"], "rpe": r["rpe"], "load": r["load"]}
                     for r in runs if r["date"] >= start and r.get("rpe") and r.get("load")],
        "status": {k: latest_g.get(k) for k in ("training_status", "load_focus", "acwr", "load_aerobic_low",
                                                 "load_aerobic_high", "load_anaerobic")},
        "scenario": sc,
    }

    # ---------------- Herstel
    rec_keys = ("date", "hrv", "hrv_base_lo", "hrv_base_hi", "hrv_status", "rhr", "sleep_h", "sleep_score", "sleep_deep_h",
                "sleep_rem_h", "sleep_light_h", "sleep_awake_h", "readiness", "readiness_level", "readiness_time", "bb_now", "bb_now_time", "bb_high", "bb_low",
                "bb_wake", "stress_avg", "steps", "respiration", "recovery_time_h")
    recovery = {
        "days": sel(days, rec_keys),
        "today": {k: last(daily[-3:], k) for k in rec_keys if k != "date"},
        "hrr_runs": [{"date": r["date"], "hrr": r["hrr60"]} for r in runs if r["date"] >= start and r.get("hrr60")],
        "averages": {k: (round(statistics.mean(v), 1) if (v := [d[k] for d in daily[-28:] if d.get(k) is not None]) else None)
                     for k in ("hrv", "rhr", "sleep_h", "sleep_score", "readiness", "bb_high", "stress_avg", "steps")},
    }

    # ---------------- Techniek
    technique = {
        "weeks": [{**l, **{k: w[k] for k in ("cadence", "stride", "vert_osc", "vert_ratio", "gct", "gct_pct", "power",
                                                "eff_power", "ef", "decoupling")}} for l, w in zip(wl, weeks)],
        "pace_ref": pace_ref, "hr_ref": hr_ref,
        "latest": {k: last([w for w in all_weeks if w["runs"]], k) for k in ("cadence", "stride", "vert_osc", "vert_ratio",
                                                                             "gct", "gct_pct", "power", "eff_power")},
    }

    # ---------------- Zones
    rs = next((x for x in data["athlete"].get("sportSettings", []) if "Run" in (x.get("types") or [])), {})
    tp_int = rs.get("threshold_pace")
    t_model = M.training_paces(tr["now"])["T"]["from"] if tr else None
    t_garmin = snap.get("lt_pace_s")
    sources = {"intervals": 1000 / tp_int if tp_int else None, "garmin": t_garmin, "model": t_model}

    def pace_zone_rows(t_s):
        if not t_s or not rs.get("pace_zones"):
            return []
        speed = 1000 / t_s
        out, lo = [], 0
        for name, hi in zip(rs.get("pace_zone_names") or [], rs["pace_zones"]):
            out.append({"name": name, "lo_pct": lo, "hi_pct": hi if hi < 900 else None,
                        "slow": fmt_time(1000 / (speed * lo / 100)) if lo else None,
                        "fast": fmt_time(1000 / (speed * hi / 100)) if hi < 900 else None})
            lo = hi
        return out

    def floor_rows(fl, names):
        rows = []
        for i, f in enumerate(fl):
            last_zone = i + 1 >= len(fl)
            to = ctx["max_hr"] if last_zone else fl[i + 1] - 1
            hi_pct = 100 if last_zone else round(fl[i + 1] / ctx["max_hr"] * 100)
            rows.append({"name": names[i] if i < len(names) else f"Zone {i + 1}", "from": f or None, "to": to,
                         "pct": f"{round(f / ctx['max_hr'] * 100)}–{hi_pct}%" if f else f"< {hi_pct}%"})
        return rows

    hr_rows_by = {}
    if garmin_floors:
        hr_rows_by["garmin"] = floor_rows(garmin_floors, ["Opwarmen", "Rustig", "Aeroob", "Drempel", "Maximaal"])
    if model_floors:
        hr_rows_by["model"] = floor_rows(model_floors, M.MODEL_HR_NAMES)
    hr_rows = []
    if active_floors:
        hr_rows = hr_rows_by["model" if use_model else "garmin"]
    else:
        prev = None
        for name, b in zip(rs.get("hr_zone_names") or [], rs.get("hr_zones") or []):
            hr_rows.append({"name": name, "from": prev + 1 if prev else None, "to": b, "pct": None})
            prev = b
    int_hist = {}
    for r in runs:
        if r.get("threshold_pace"):
            int_hist.setdefault(M.week_start(dt.date.fromisoformat(r["date"])).isoformat(), []).append(1000 / r["threshold_pace"])
    fitmap = {f["week"]: f["fit"] for f in (tr["fit"] if tr else [])}
    g_hist = {}
    for x in snap.get("lt_hist") or []:
        g_hist[M.week_start(dt.date.fromisoformat(x["date"])).isoformat()] = x["pace_s"]
    zhist = [{"label": l["label"], "range": l["range"],
              "intervals": round(statistics.median(int_hist[l["week"]])) if l["week"] in int_hist else None,
              "garmin": g_hist.get(l["week"]),
              "model": round(M.training_paces(fitmap[l["week"]])["T"]["from"]) if l["week"] in fitmap else None}
             for l in wl]
    if tr and zhist:  # laatste week: gebruik "nu" (incl. beste recente inspanning)
        zhist[-1]["model"] = round(t_model)
    dp = lambda v: {k: {**x, "from": fmt_time(x["from"]), "to": fmt_time(x["to"]) if x["to"] else None}
                    for k, x in M.training_paces(v).items()}
    since = min(int_hist) if int_hist else None
    def zone_time(key):
        tot = [0] * len(hr_rows or [0] * 7)
        for r in runs:
            if r["date"] >= start:
                for i, z in enumerate((r.get(key) or [])[:len(tot)]):
                    tot[i] += z or 0
        all_s = sum(tot) or 1
        return [{"min": round(t / 60), "pct": round(t / all_s * 100)} for t in tot] if sum(tot) else None

    period_ids = [r["id"] for r in runs if r["date"] >= start]

    def pace_time(t_s):
        tot = M.pace_zone_time(period_ids, t_s, rs.get("pace_zones") or [77.5, 87.7, 94.3, 100, 103.4, 111.5, 999])
        if not tot or not sum(tot):
            return None
        return [{"min": round(t / 60), "pct": round(t / sum(tot) * 100)} for t in tot]

    zones = {
        "time_hr": zone_time("zones"),
        "hr_zones_by": hr_rows_by, "hr_active": "model" if use_model else ("garmin" if garmin_floors else "intervals"),
        "time_pace": {"garmin": pace_time(t_garmin), "model": pace_time(t_model)},
        "sources": {k: fmt_time(v) if v else None for k, v in sources.items()},
        "sources_s": {k: round(v) if v else None for k, v in sources.items()},
        "intervals_since": " · ".join(M.week_label(since)) if since and len({round(v) for vs in int_hist.values() for v in vs}) == 1 else None,
        "garmin_lt_hr": snap.get("lt_hr"), "lthr": ctx.get("lthr"), "max_hr": ctx["max_hr"],
        "hr_source": ctx.get("hr_source"), "hr_method": ctx.get("hr_method"), "rest_hr": round(ctx["rest_hr"]),
        "pace_zones": {k: pace_zone_rows(v) for k, v in sources.items()},
        "hr_zones": hr_rows,
        "daniels_now": dp(tr["now"]) if tr else None,
        "daniels_12": dp(tr["at"](12)[0]) if tr else None,
        "vdot_now": round(tr["now"], 1) if tr else None, "vdot_12": round(tr["at"](12)[0], 1) if tr else None,
        "history": zhist,
    }

    # Tempoverdeling per week in Training: met de model-drempel (niet intervals.icu)
    bounds = rs.get("pace_zones") or [77.5, 87.7, 94.3, 100, 103.4, 111.5, 999]
    for w in training["weeks"]:
        ids = [r["id"] for r in runs if M.week_start(dt.date.fromisoformat(r["date"])).isoformat() == w["week"]]
        tot = M.pace_zone_time(ids, t_model, bounds) if ids and t_model else None
        w["pz7"] = [round(t / sum(tot) * 100) for t in tot] if tot and sum(tot) else None
    zones["easy_label"] = "Z1–Z2" if use_model else ("Z1–Z3" if garmin_floors else "Z1–Z2")

    # ---------------- Analyse, suggestie, techniek-focus
    tp_now = M.training_paces(tr["now"]) if tr else None
    paces = {"E_fast": tp_now["E"]["from"], "E_slow": tp_now["E"]["to"], "M": tp_now["M"]["from"],
             "T": tp_now["T"]["from"], "I": tp_now["I"]["from"]} if tp_now else None
    daily_by = {x["date"]: x for x in daily}
    # Analyse, suggestie en Garmin-workouts gebruiken altijd de model-zones (los van de weergavekeuze)
    model_rows = hr_rows_by.get("model") or hr_rows
    if model_floors and not use_model:
        runs_m = []
        for r in runs:
            st = store.streams(r["id"])
            z = M.hr_zone_seconds(st["heartrate"], st["time"], model_floors) if st.get("heartrate") and st.get("time") else r["zones"]
            runs_m.append({**r, "zones": z})
    else:
        runs_m = runs
    analyses = {}
    if paces and model_rows:
        for r in runs_m:
            analyses[r["id"]] = analysis.analyze_session(r, runs_m, daily_by, model_rows, paces)
    def pace_txt(steps):
        for st in steps:
            for s2 in ([st] if st["kind"] != "repeat" else st["steps"]):
                if s2.get("pace"):
                    s2["pace_txt"] = f"{fmt_time(min(s2['pace']))}–{fmt_time(max(s2['pace']))}"

    plan = None
    if paces and model_rows and runs and tr:
        plan = PL.build(runs_m, all_weeks, daily_by, model_rows, paces, tr["now"], today, goal, settings)
        if plan:
            pushed_all = load_pushed()
            for w in (plan["this_week"], plan["next_week"]):
                for d in w["days"]:
                    pace_txt(d["steps"])
                    pw = pushed_all.get(d["date"])
                    d["pushed"] = bool(pw and pw.get("title") == d["title"])
    suggestion = None
    if paces and model_rows and runs:
        suggestion = analysis.suggest(runs_m, daily_by, model_rows, paces, today, tuple(settings.get("long_days", [4, 5, 6])), plan)
        pace_txt(suggestion["steps"])
        pushed = load_pushed().get(suggestion["date"])
        suggestion["pushed"] = pushed if pushed and pushed.get("title") == suggestion["title"] else None
        suggestion["pushed_other"] = pushed["title"] if pushed and pushed.get("title") != suggestion["title"] else None
        suggestion["garmin_linked"] = data.get("garmin_linked")
    tech_focus = analysis.technique_focus(runs, today)
    technique["focus"] = tech_focus
    zones["garmin_watch"] = garmin_watch_status(ctx, hr_rows_by.get("model"))

    # ---------------- Overzicht
    this_w = all_weeks[-1] if all_weeks else {}
    if use_model:
        zl = ("Z1–Z2", "Z3", hr_rows[2]["from"])
    elif garmin_floors and len(hr_rows) >= 4:
        zl = ("Z1–Z3", "Z4", hr_rows[3]["from"])
    else:
        zl = ("Z1–Z2", "Z3", None)
    ins = insights.build(all_weeks[-max(period_weeks, 4):], runs, tr, hr_ref, pace_ref, data_weeks, daily, snap, model_now, zl)
    spark_weeks = all_weeks[-12:]
    overview = {
        "kpis": {
            "vdot": {"value": perf.get("vdot", {}).get("now"), "spark": [w["vdot"] for w in spark_weeks]},
            "vo2max": {"value": perf["vo2max"], "spark": weekly_from_daily(daily, "vo2max", spark_weeks, max)},
            "readiness": {"value": last(daily[-3:], "readiness"), "level": last(daily[-3:], "readiness_level"),
                          "spark": weekly_from_daily(daily, "readiness", spark_weeks)},
            "km": {"value": round(avg_km, 1), "spark": [w["km"] for w in spark_weeks]},
            "ctl": {"value": last(daily, "ctl"), "spark": weekly_from_daily(daily, "ctl", spark_weeks, max)},
            "hrv": {"value": last(daily[-3:], "hrv"), "spark": weekly_from_daily(daily, "hrv", spark_weeks)},
        },
        "this_week": {"week": M.week_start(today).isoformat(), "label": this_w.get("label"), "range": this_w.get("range"), "km": this_w.get("km"),
                      "runs": this_w.get("runs"), "hours": this_w.get("hours"), "load": this_w.get("load"),
                      "elev": this_w.get("elev"), "avg_km": round(avg_km, 1)},
        "insights": ins,
        "suggestion": suggestion,
        "last_session": ({"id": runs[-1]["id"], "name": runs[-1]["name"], "date": runs[-1]["date"],
                          "km": runs[-1]["km"], "minutes": runs[-1]["minutes"], "pace": fmt_time(runs[-1]["pace_s_km"]),
                          "avg_hr": runs[-1]["avg_hr"], "te": runs[-1]["te_aerobic"], "te_label": runs[-1]["te_label"],
                          **analyses[runs[-1]["id"]]} if runs and runs[-1]["id"] in analyses else None),
        "tech_focus": tech_focus,
    }

    activities = [{k: r[k] for k in ("id", "date", "start", "name", "km", "minutes", "avg_hr", "max_hr", "pace_s_km",
                                      "gap_s_km", "load", "vdot_race", "vdot_hr_cal", "decoupling", "cadence", "race",
                                      "power", "np", "rpe", "feel", "trimp", "elev", "hrr60", "te_aerobic", "te_anaerobic",
                                      "te_label", "intervals", "calories", "stamina_end")}
                  | {"efforts": [{"label": f"{D / 1000:g} km", "time": fmt_time(e["time"]), "vdot": e["vdot"], "hard": e["hard"]}
                                 for D, e in sorted(r["efforts"].items())],
                     "analysis": analyses.get(r["id"])}
                  for r in reversed(runs)]

    return {
        "today": today.isoformat(), "athlete": data["athlete"].get("name"), "meta": data["meta"],
        "garmin_linked": data.get("garmin_linked"), "mode": data["meta"].get("mode", "intervals"),
        "profile": paths.PROFILE, "period": period_weeks, "ctx": ctx,
        "goal": goal_out, "plan": plan, "overview": overview, "performance": perf, "training": training,
        "recovery": recovery, "technique": technique, "zones": zones, "activities": activities, "labels": M.RACE_LABELS,
        # Route: startpunt + afstand van de suggestie; de ORS-sleutel alleen lokaal (online zit hij versleuteld in cfg.enc)
        "route": {"home": settings.get("home"), "est_km": (suggestion or {}).get("est_km"),
                  "heat": M.heat_cells(runs, store.route_center()),
                  "ors_key": None if os.environ.get("GITHUB_ACTIONS") else load_env().get("ORS_API_KEY")},
    }


# --------------------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _guard(self, fn):
        try:
            self._json(fn())
        except IntervalsError as e:
            self._json({"error": str(e)}, 502)
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        q = urllib.parse.parse_qs(query)
        if path in ("/", "/index.html"):
            with open(os.path.join(STATIC, "index.html"), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/dashboard":
            weeks = int((q.get("weeks") or ["12"])[0])
            km = float(q["km"][0]) if q.get("km") else None
            self._guard(lambda: build_payload(weeks, km))
        elif path == "/api/run":
            self._guard(lambda: M.run_detail((q.get("id") or [""])[0]))
        else:
            self.send_error(404)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"):
            return self._json({"error": "Verboden origin"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/sync":
            self._guard(store.sync)
        elif self.path == "/api/goal":
            self._guard(lambda: save_goal(body))
        elif self.path == "/api/settings":
            self._guard(lambda: save_settings(body))
        elif self.path == "/api/push_workout":
            self._guard(lambda: push_workout(body))
        elif self.path == "/api/unpush_workout":
            self._guard(lambda: unpush_workout(body))
        elif self.path == "/api/garmin_zones":
            self._guard(lambda: set_garmin_zones(body))
        else:
            self.send_error(404)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Prestatiedashboard draait op {url}  (Ctrl+C om te stoppen)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
