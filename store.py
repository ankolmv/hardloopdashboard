"""Lokale cache van intervals.icu- en Garmin-data in de map data/.

- intervals.icu: activiteiten, wellness en atleet worden bij elke sync vernieuwd (klein);
  streams van runs worden één keer opgehaald.
- Garmin Connect: dagsamenvattingen worden één keer per dag opgehaald (de laatste 3 dagen
  altijd opnieuw, omdat Garmin die nog bijwerkt); momentopnames worden per sync bewaard.
"""
import datetime as dt
import json
import os
import threading

import garmin_client
import strava_client
from intervals_client import IntervalsClient

import paths

DATA = paths.DATA
HISTORY_START = "2020-01-01"
GARMIN_DAYS = 90
_lock = threading.Lock()


def _path(name):
    return os.path.join(DATA, name)


def _read(name, default=None):
    p = _path(name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _write(name, obj):
    p = _path(name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)


def has_data(a):
    """Strava-activiteiten komen via de API zonder inhoud binnen."""
    return bool(a.get("type")) and a.get("moving_time")


def is_run(a):
    return "Run" in (a.get("type") or "")


def sync_intervals():
    c = IntervalsClient()
    today = dt.date.today().isoformat()
    activities = c.activities(HISTORY_START, today)
    _write("athlete.json", c.athlete())
    _write("activities.json", activities)
    _write("wellness.json", c.wellness(HISTORY_START, today))
    new = 0
    for a in activities:
        if not (has_data(a) and is_run(a)):
            continue
        name = os.path.join("streams", f"{a['id']}.json")
        if os.path.exists(_path(name)):
            continue
        _write(name, _streams_dict(c.activity_streams(a["id"])))
        new += 1
    # Eenmalig: GPS (lat/lng) aanvullen voor runs die al in de cache staan zonder GPS
    gps = 0
    for a in activities:
        if not (has_data(a) and is_run(a)):
            continue
        name = os.path.join("streams", f"{a['id']}.json")
        s = _read(name, None)
        if s is None or "lat" in s:
            continue
        extra = _streams_dict(c.activity_streams(a["id"], "latlng"))
        s.update({k: v for k, v in extra.items() if k in ("lat", "lng")} or {"lat": None, "lng": None})
        _write(name, s)
        gps += 1
    return {"activities": len(activities), "with_data": sum(1 for a in activities if has_data(a)),
            "new_streams": new, "gps_backfill": gps}


def _streams_dict(raw):
    """intervals.icu-streams naar {type: data}; latlng wordt gesplitst in lat (data) en lng (data2)."""
    out = {}
    for s in raw or []:
        if s.get("type") == "latlng":
            out["lat"], out["lng"] = s.get("data"), s.get("data2")
        else:
            out[s["type"]] = s.get("data")
    return out


def sync_garmin():
    if not garmin_client.available():
        return {"garmin": "niet gekoppeld"}
    g = garmin_client.connect()
    today = dt.date.today()
    days = 0
    for i in range(GARMIN_DAYS):
        d = today - dt.timedelta(days=i)
        name = os.path.join("garmin", "daily", f"{d.isoformat()}.json")
        if i >= 3 and os.path.exists(_path(name)):
            continue
        _write(name, garmin_client.fetch_day(g, d))
        days += 1
    snap = garmin_client.fetch_snapshot(g, today)
    snap["name"] = garmin_client._try(g.get_full_name)
    hist = [s for s in _read(os.path.join("garmin", "snapshots.json"), []) if s.get("date") != snap["date"]]
    _write(os.path.join("garmin", "snapshots.json"), hist + [snap])
    acts = garmin_client.fetch_activities(g, today - dt.timedelta(days=GARMIN_DAYS), today)
    old = {a["garmin_id"]: a for a in _read(os.path.join("garmin", "activities.json"), [])}
    old.update({a["garmin_id"]: a for a in acts})
    _write(os.path.join("garmin", "activities.json"), list(old.values()))
    if not intervals_configured():
        write_garmin_athlete(snap, list(old.values()))
        write_garmin_wellness()  # eerst rusthartslag beschikbaar maken voor de belastingsschatting
    filled = fill_missing_runs(g, list(old.values()))
    # Extra's voor de trainingsanalyse (Performance Condition, weer) van recente runs
    for ga in old.values():
        if "run" not in (ga.get("type") or "") or not ga.get("start"):
            continue
        if (today - dt.date.fromisoformat(ga["start"][:10])).days > 21:
            continue
        name = os.path.join("garmin", "extra", f"{ga['garmin_id']}.json")
        if not os.path.exists(_path(name)):
            _write(name, garmin_client.fetch_run_extra(g, ga["garmin_id"]))
    if not intervals_configured():
        write_garmin_wellness()
    return {"garmin": "ok", "garmin_days": days, "garmin_activities": len(acts), "garmin_filled_runs": filled}


def _ts(s):
    try:
        return dt.datetime.fromisoformat((s or "")[:19].replace(" ", "T"))
    except ValueError:
        return None


def _has_match(start, runs, secs=300):
    t = _ts(start)
    return t is not None and any((u := _ts(r.get("start_date_local"))) and abs((u - t).total_seconds()) <= secs for r in runs)


def fill_missing_runs(g, garmin_acts):
    """Haal Garmin-runs op die in intervals.icu ontbreken of alleen als lege Strava-kopie staan."""
    intervals_runs = [a for a in _read("activities.json", []) if has_data(a) and is_run(a)]
    athlete = _read("athlete.json", {})
    rs = next((s for s in athlete.get("sportSettings", []) if "Run" in (s.get("types") or [])), {})
    rests = [w["restingHR"] for w in _read("wellness.json", [])[-30:] if w.get("restingHR")]
    ctx = {"rest_hr": sorted(rests)[len(rests) // 2] if rests else 50, "lthr": rs.get("lthr"), "hr_zones": rs.get("hr_zones")}
    n = 0
    for ga in garmin_acts:
        if "run" not in (ga.get("type") or "") or _has_match(ga.get("start"), intervals_runs):
            continue
        name = os.path.join("garmin", "runs", f"{ga['garmin_id']}.json")
        if os.path.exists(_path(name)) and "lat" in _read(os.path.join("streams", f"g{ga['garmin_id']}.json"), {}):
            continue
        act, streams = garmin_client.fetch_run(g, ga["garmin_id"], ctx)
        _write(os.path.join("streams", f"{act['id']}.json"), streams)
        _write(name, act)
        n += 1
    return n


def garmin_runs():
    d = _path(os.path.join("garmin", "runs"))
    if not os.path.isdir(d):
        return []
    return [_read(os.path.join("garmin", "runs", fn)) for fn in os.listdir(d) if fn.endswith(".json")]


# --------------------------------------------------------------------------- alleen-Garmin-modus
HR_ZONE_NAMES = ["Recovery", "Aerobic", "Tempo", "SubThreshold", "SuperThreshold", "Aerobic Capacity", "Anaerobic"]


def intervals_configured():
    from intervals_client import load_env
    e = load_env()
    return bool(e.get("INTERVALS_ATHLETE_ID") and e.get("INTERVALS_API_KEY"))


def write_garmin_athlete(snap, garmin_acts):
    """Atleetprofiel zoals intervals.icu het zou leveren, afgeleid uit Garmin."""
    max_hr = (snap.get("hr_zones") or {}).get("max") or \
        max([a.get("max_hr") or 0 for a in garmin_acts if "run" in (a.get("type") or "")] or [0]) or 190
    lthr = snap.get("lt_hr") or round(max_hr * 0.9)
    zones = [round(lthr * p) for p in (0.85, 0.89, 0.94, 0.99, 1.02, 1.06)] + [max_hr]  # Friel-indeling (standaard intervals.icu)
    _write("athlete.json", {"name": snap.get("name") or "", "sportSettings": [{
        "types": ["Run"], "max_hr": max_hr, "lthr": lthr,
        "threshold_pace": round(1000 / snap["lt_pace_s"], 4) if snap.get("lt_pace_s") else None,
        "hr_zones": zones, "hr_zone_names": HR_ZONE_NAMES,
        "pace_zones": [77.5, 87.7, 94.3, 100.0, 103.4, 111.5, 999.0],
        "pace_zone_names": ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5a", "Zone 5b", "Zone 5c"],
    }]})


def write_garmin_wellness():
    """Fitheid (CTL, 42 d) en vermoeidheid (ATL, 7 d) zelf berekenen uit de belasting van de runs."""
    loads = {}
    for a in garmin_runs():
        if a and a.get("icu_training_load"):
            d = a["start_date_local"][:10]
            loads[d] = loads.get(d, 0) + a["icu_training_load"]
    gdir = _path(os.path.join("garmin", "daily"))
    days = sorted(fn[:-5] for fn in os.listdir(gdir) if fn.endswith(".json")) if os.path.isdir(gdir) else []
    if not days:
        _write("wellness.json", [])
        return
    d, end = dt.date.fromisoformat(days[0]), dt.date.today()
    ctl = atl = 0.0
    out = []
    while d <= end:
        ds = d.isoformat()
        load = loads.get(ds, 0)
        ctl += (load - ctl) / 42
        atl += (load - atl) / 7
        g = _read(os.path.join("garmin", "daily", f"{ds}.json"), {})
        out.append({"id": ds, "ctl": round(ctl, 2), "atl": round(atl, 2), "restingHR": g.get("resting_hr"),
                    "hrv": g.get("hrv_night"), "sleepSecs": g.get("sleep_s"), "sleepScore": g.get("sleep_score"),
                    "steps": g.get("steps"), "vo2max": g.get("vo2max")})
        d += dt.timedelta(days=1)
    _write("wellness.json", out)


def _home():
    p = os.path.join(paths.BASE, "settings.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("home")
    return None


def route_center():
    """Startpunt uit de instellingen, anders het begin van de laatste run met GPS."""
    home = _home()
    if home:
        return home
    for a in sorted(_read("activities.json", []), key=lambda a: a.get("start_date_local") or "", reverse=True):
        s = streams(a["id"]) if has_data(a) and is_run(a) else {}
        if s.get("lat") and s.get("lng") and s["lat"][0] is not None:
            return [s["lat"][0], s["lng"][0]]
    return None


def sync_strava():
    """Populaire hardloopsegmenten rond het startpunt; eens per 7 dagen of als het startpunt verschuift."""
    if not strava_client.available():
        return {"strava": "niet gekoppeld"}
    center = route_center()
    if not center:
        return {"strava": "geen startpunt"}
    cur = _read(os.path.join("strava", "segments.json"), {}) or {}
    old_c = cur.get("center") or [0, 0]
    moved = abs(old_c[0] - center[0]) > 0.01 or abs(old_c[1] - center[1]) > 0.015
    age = dt.datetime.now() - dt.datetime.fromisoformat(cur["fetched_at"]) if cur.get("fetched_at") else None
    if not moved and age is not None and age < dt.timedelta(days=7):
        return {"strava": "ok (cache)", "strava_segments": len(cur.get("segments") or [])}
    segs = strava_client.explore_around(center)
    _write(os.path.join("strava", "segments.json"), {"center": center, "segments": segs,
                                                     "fetched_at": dt.datetime.now().isoformat(timespec="seconds")})
    return {"strava": "ok", "strava_segments": len(segs)}


def sync():
    with _lock:
        if intervals_configured():
            meta = {"mode": "intervals", **sync_intervals()}
        else:
            meta = {"mode": "garmin", "activities": 0, "with_data": 0, "new_streams": 0}
            if not os.path.exists(_path("activities.json")):
                _write("activities.json", [])
        try:
            meta.update(sync_garmin())
        except Exception as e:  # noqa: BLE001  – Garmin mag de sync nooit breken
            meta.update({"garmin": f"fout: {e}"})
        try:
            meta.update(sync_strava())
        except Exception as e:  # noqa: BLE001  – Strava mag de sync nooit breken
            meta.update({"strava": f"fout: {e}"})
        meta["synced_at"] = dt.datetime.now().isoformat(timespec="seconds")
        _write("meta.json", meta)
        return meta


def load():
    """Alles uit de cache; None als er nog nooit gesynchroniseerd is."""
    meta = _read("meta.json")
    if not meta:
        return None
    gdir = _path(os.path.join("garmin", "daily"))
    daily = {}
    if os.path.isdir(gdir):
        for fn in os.listdir(gdir):
            if fn.endswith(".json"):
                daily[fn[:-5]] = _read(os.path.join("garmin", "daily", fn), {})
    activities = _read("activities.json", [])
    # Aangevuld uit Garmin, tenzij intervals.icu de run inmiddels zelf met data heeft
    intervals_runs = [a for a in activities if has_data(a) and is_run(a)]
    extra = [a for a in garmin_runs() if a and not _has_match(a.get("start_date_local"), intervals_runs)]
    return {
        "meta": meta,
        "athlete": _read("athlete.json", {}),
        "activities": activities + extra,
        "wellness": _read("wellness.json", []),
        "garmin_daily": daily,
        "garmin_snapshots": _read(os.path.join("garmin", "snapshots.json"), []),
        "garmin_activities": _read(os.path.join("garmin", "activities.json"), []),
        "garmin_linked": garmin_client.available(),
        "garmin_extra": _read_dir(os.path.join("garmin", "extra")),
        "strava_segments": (_read(os.path.join("strava", "segments.json"), {}) or {}).get("segments") or [],
        "strava_linked": strava_client.available(),
    }


def _read_dir(name):
    d = _path(name)
    if not os.path.isdir(d):
        return {}
    return {fn[:-5]: _read(os.path.join(name, fn), {}) for fn in os.listdir(d) if fn.endswith(".json")}


def streams(activity_id):
    return _read(os.path.join("streams", f"{activity_id}.json"), {})
