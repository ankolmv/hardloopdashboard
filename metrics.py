"""Prestatieberekeningen per run, per week en per dag (hardlopen).

Prestatiemaat is VDOT (Daniels & Gilbert): een 'effectieve VO2max' die over afstanden
vergelijkbaar is en direct naar wedstrijdtijden te vertalen.
"""
import datetime as dt
import math
import statistics

import store

RACE_DISTANCES = {"5k": 5000.0, "10k": 10000.0, "hm": 21097.5, "m": 42195.0}
RACE_LABELS = {"5k": "5 km", "10k": "10 km", "hm": "Halve marathon", "m": "Marathon"}
EFFORT_DISTANCES = [1000.0, 3000.0, 5000.0, 10000.0, 21097.5]
# Minimale snelheid t.o.v. drempeltempo om een beste effort als (bijna) maximaal te tellen
EFFORT_SPEED_FACTOR = {1000.0: 1.08, 3000.0: 1.04, 5000.0: 1.02, 10000.0: 0.99, 21097.5: 0.95}
MONTHS = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


# --------------------------------------------------------------------------- Daniels
def vo2_at_speed(v_m_min):
    return -4.60 + 0.182258 * v_m_min + 0.000104 * v_m_min ** 2


def pct_vo2max(t_min):
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot_from_race(dist_m, time_s):
    t = time_s / 60
    return vo2_at_speed(dist_m / t) / pct_vo2max(t)


def race_time(vdot, dist_m):
    """Tijd (s) voor `dist_m` bij gegeven VDOT (bisectie)."""
    lo, hi = 60.0, 60 * 60 * 10.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if vdot_from_race(dist_m, mid) > vdot:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def speed_for_vo2(vo2):
    """Inverse van vo2_at_speed (m/min)."""
    a, b, c = 0.000104, 0.182258, -4.60 - vo2
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def training_paces(vdot):
    """Trainingstempo's (s/km) volgens Daniels bij een gegeven VDOT."""
    sp = lambda pct: 60000 / speed_for_vo2(vdot * pct)
    return {
        "E": {"name": "Rustig (Easy)", "from": sp(0.74), "to": sp(0.59), "doel": "Duurlopen, herstel, aerobe basis"},
        "M": {"name": "Marathontempo", "from": race_time(vdot, 42195) / 42.195, "to": None, "doel": "Lange tempo-blokken"},
        "T": {"name": "Drempel (Threshold)", "from": sp(0.88), "to": None, "doel": "Tempoduurloop, 20-40 min of blokken van 5-10 min"},
        "I": {"name": "Interval", "from": sp(0.975), "to": None, "doel": "VO2max-blokken van 3-5 min"},
        "R": {"name": "Herhalingen (Repetition)", "from": race_time(vdot, 1609.34) / 1.60934, "to": None, "doel": "Korte snelle stukken 200-400 m, snelheid en economie"},
    }


# Grenzen als fractie van VO2max (Daniels): onder E = herstel, E = duur, M = tempo, T = drempel, daarboven VO2max
MODEL_HR_PCTS = (0.59, 0.745, 0.83, 0.89)
MODEL_HR_NAMES = ["Herstel", "Duur (E)", "Tempo / marathon (M)", "Drempel (T)", "VO2max (I)"]


def hr_at_pct(vdot, pct, rest, max_hr):
    """Hartslag bij een % van VO2max, via %VO2-reserve ≈ %hartslagreserve (Swain)."""
    vo2r = (vdot * pct - 3.5) / (vdot - 3.5)
    return rest + vo2r * (max_hr - rest)


def model_hr_floors(vdot, rest, max_hr):
    """Ondergrenzen van 5 hartslagzones, afgeleid uit je VDOT."""
    return [0] + [round(hr_at_pct(vdot, p, rest, max_hr)) for p in MODEL_HR_PCTS]


# --------------------------------------------------------------------------- weken
def week_start(d):
    return d - dt.timedelta(days=d.weekday())


def week_label(monday):
    """'wk 42' en '12–18 okt' voor een maandag (iso-string of date)."""
    m = dt.date.fromisoformat(monday) if isinstance(monday, str) else monday
    s = m + dt.timedelta(days=6)
    rng = (f"{m.day}–{s.day} {MONTHS[s.month - 1]}" if m.month == s.month
           else f"{m.day} {MONTHS[m.month - 1]} – {s.day} {MONTHS[s.month - 1]}")
    return f"wk {m.isocalendar()[1]}", rng


def fill_weeks(rows, zero_keys, until=None):
    """Lege weken toevoegen zodat grafieken een doorlopende tijdas hebben."""
    if not rows:
        return rows
    until = until or week_start(dt.date.today())
    by = {r["week"]: r for r in rows}
    d = dt.date.fromisoformat(rows[0]["week"])
    template = {k: None for k in rows[0]}
    out = []
    while d <= until:
        k = d.isoformat()
        out.append(by.get(k) or {**template, "week": k, **{z: 0 for z in zero_keys}})
        d += dt.timedelta(weeks=1)
    for r in out:
        r["label"], r["range"] = week_label(r["week"])
    return out


# --------------------------------------------------------------------------- helpers
def date_of(a):
    return dt.date.fromisoformat(a["start_date_local"][:10])


def is_run(a):
    return "Run" in (a.get("type") or "")


def resting_hr_on(wellness_by_date, d, fallback):
    for i in range(0, 8):
        w = wellness_by_date.get((d - dt.timedelta(days=i)).isoformat())
        if w and w.get("restingHR"):
            return w["restingHR"]
    return fallback


def best_efforts(dist, time, hr=None):
    """Snelste tijd per doelafstand (twee-pointer over de afstand-stream)."""
    out = {}
    n = len(dist)
    if n < 2:
        return out
    for D in EFFORT_DISTANCES:
        if dist[-1] < D:
            continue
        best, j, bi = None, 0, None
        for i in range(n):
            while j < n and dist[j] - dist[i] < D:
                j += 1
            if j >= n:
                break
            over = dist[j] - dist[i] - D
            seg = dist[j] - dist[j - 1] or 1
            t = time[j] - time[i] - over / seg * (time[j] - time[j - 1])
            if best is None or t < best:
                best, bi = t, (i, j)
        if best:
            hr_avg = None
            if hr and bi:
                vals = [h for h in hr[bi[0]:bi[1]] if h]
                hr_avg = statistics.mean(vals) if vals else None
            out[D] = {"time": best, "hr": hr_avg}
    return out


def hr_zone_seconds(hr, time, floors):
    """Seconden per hartslagzone (Garmin: 5 zones met ondergrenzen). Onder zone 1 telt als Z1."""
    tot = [0.0] * len(floors)
    for i in range(1, min(len(hr), len(time))):
        h, dtm = hr[i], (time[i] or 0) - (time[i - 1] or 0)
        if not h or dtm <= 0 or dtm > 30:
            continue
        z = max(0, sum(1 for f in floors if h >= f) - 1)
        tot[z] += dtm
    return tot


def splits_per_km(s):
    """Splits per volle km uit de streams: tijd, hartslag, cadans, vermogen, hoogteverschil."""
    dist, time = s.get("distance") or [], s.get("time") or []
    hr, cad, w, alt = (s.get(k) or [] for k in ("heartrate", "cadence", "watts", "altitude"))
    out, start, km = [], 0, 1
    avg = lambda xs, a, b: round(statistics.mean(v for v in xs[a:b] if v)) if xs and any(xs[a:b]) else None
    for i, d in enumerate(dist):
        if d is not None and d >= km * 1000:
            out.append({"km": km, "time": time[i] - time[start], "hr": avg(hr, start, i),
                        "cadence": (avg(cad, start, i) or 0) * 2 or None, "watts": avg(w, start, i),
                        "elev": round((alt[i] or 0) - (alt[start] or 0)) if alt else None})
            start, km = i, km + 1
    return out


def normalized_power(watts):
    vals = [w or 0 for w in watts]
    if len(vals) < 60:
        return None
    acc, roll = sum(vals[:30]), []
    for i in range(30, len(vals)):
        roll.append((acc / 30) ** 4)
        acc += vals[i] - vals[i - 30]
    return round(statistics.mean(roll) ** 0.25) if roll else None


def match_garmin(run_start, garmin_acts):
    """Garmin-activiteit met starttijd binnen 2 minuten."""
    try:
        t = dt.datetime.fromisoformat(run_start[:19])
    except ValueError:
        return None
    for g in garmin_acts:
        try:
            gt = dt.datetime.fromisoformat((g.get("start") or "")[:19])
        except ValueError:
            continue
        if abs((gt - t).total_seconds()) <= 120:
            return g
    return None


# --------------------------------------------------------------------------- per run
def analyze_run(a, ctx):
    d = date_of(a)
    s = store.streams(a["id"])
    dist, time, hr, vel = (s.get(k) or [] for k in ("distance", "time", "heartrate", "velocity_smooth"))
    watts = s.get("watts") or []
    max_hr = ctx["max_hr"] if ctx.get("hr_source") == "garmin" else (a.get("athlete_max_hr") or ctx["max_hr"])
    rest = resting_hr_on(ctx["wellness"], d, a.get("icu_resting_hr") or ctx["rest_hr"])
    tp = a.get("threshold_pace") or ctx["tp"]
    km = (a.get("distance") or 0) / 1000
    mins = (a.get("moving_time") or 0) / 60
    pw = [x for x in watts if x]
    g = match_garmin(a.get("start_date_local") or "", ctx["garmin_acts"]) or {}
    r = {
        "id": a["id"], "date": d.isoformat(), "start": a.get("start_date_local"), "name": a.get("name"),
        "km": round(km, 2), "minutes": round(mins, 1), "load": a.get("icu_training_load"),
        "race": bool(a.get("race")), "avg_hr": a.get("average_heartrate"), "max_hr": a.get("max_heartrate"),
        "pace_s_km": 1000 / a["pace"] if a.get("pace") else None,
        "gap_s_km": 1000 / a["gap"] if a.get("gap") else None,
        "cadence": (a.get("average_cadence") or 0) * 2 or None,  # Garmin geeft per been
        "stride": a.get("average_stride"), "vert_osc": a.get("average_vertical_oscillation"),
        "vert_ratio": a.get("average_vertical_ratio"), "gct": a.get("average_stance_time"),
        "gct_pct": a.get("average_stance_time_percent"),
        "elev": round(a["total_elevation_gain"]) if a.get("total_elevation_gain") else 0,
        "zones": (hr_zone_seconds(hr, time, ctx["hr_floors"]) if ctx.get("hr_floors") and hr and time
                  else a.get("icu_hr_zone_times")),
        "pace_zones": None,  # tempoverdeling wordt in app.py met de model-drempel berekend (niet die van intervals.icu)
        "polarization": a.get("polarization_index"), "rpe": a.get("icu_rpe"), "feel": a.get("feel"),
        "trimp": round(a["trimp"]) if a.get("trimp") else None, "intensity": a.get("icu_intensity"),
        "hrr60": (a.get("icu_hrr") or {}).get("hrr"), "calories": a.get("calories"),
        "intervals": a.get("interval_summary") or [], "laps": a.get("icu_lap_count"),
        "power": round(statistics.mean(pw)) if pw else None, "np": normalized_power(watts) if pw else None,
        "te_aerobic": round(g["te_aerobic"], 1) if g.get("te_aerobic") is not None else None,
        "te_anaerobic": round(g["te_anaerobic"], 1) if g.get("te_anaerobic") is not None else None,
        "te_label": g.get("te_label"), "garmin_load": round(g["garmin_load"]) if g.get("garmin_load") else None,
        "stamina_end": g.get("stamina_end"), "garmin_id": g.get("garmin_id"),
        **{k: v for k, v in (ctx.get("garmin_extra") or {}).get(str(g.get("garmin_id")), {}).items()},
        "threshold_pace": a.get("threshold_pace"),
        "vdot_race": None, "vdot_hr": None, "efforts": {}, "decoupling": None, "ef": None, "eff_power": None,
    }
    if r["power"] and a.get("average_speed"):
        r["eff_power"] = round(a["average_speed"] * 60 / r["power"], 3)  # m/min per watt

    if dist and time:
        for D, e in best_efforts(dist, time, hr).items():
            v = D / e["time"]
            vd = vdot_from_race(D, e["time"])
            hr_hard = 0.95 * ctx["lthr"] if ctx.get("lthr") else 0.86 * max_hr  # ~drempelhartslag
            hard = (e["hr"] and e["hr"] >= hr_hard) or (tp and v >= tp * EFFORT_SPEED_FACTOR[D]) or r["race"]
            r["efforts"][int(D)] = {"time": round(e["time"]), "vdot": round(vd, 2), "hard": bool(hard)}
            if hard and (r["vdot_race"] is None or vd > r["vdot_race"]):
                r["vdot_race"] = round(vd, 2)

    if mins >= 20 and hr and vel and time:
        idx = [i for i, t in enumerate(time) if t >= 300 and hr[i] and vel[i] and vel[i] > 1.5]
        if len(idx) > 300:
            v_mean = statistics.mean(vel[i] for i in idx)
            h_mean = statistics.mean(hr[i] for i in idx)
            gap_ratio = (a["gap"] / a["pace"]) if a.get("gap") and a.get("pace") else 1.0
            v_mmin = v_mean * gap_ratio * 60
            hrr = (h_mean - rest) / (max_hr - rest) if max_hr > rest else None
            if hrr and 0.5 <= hrr <= 0.92:
                r["vdot_hr"] = round((vo2_at_speed(v_mmin) - 3.5) / hrr + 3.5, 2)
            r["ef"] = round(v_mmin / h_mean, 4)
            if mins >= 45:
                half = len(idx) // 2
                ef = lambda ids: statistics.mean(vel[i] for i in ids) / statistics.mean(hr[i] for i in ids)
                e1, e2 = ef(idx[:half]), ef(idx[half:])
                r["decoupling"] = round((e1 - e2) / e1 * 100, 1)
    return r


def pace_zone_time(run_ids, threshold_s_km, pct_bounds):
    """Tijd per tempozone (seconden) uit de snelheids-streams, voor een gegeven drempeltempo.

    pct_bounds: bovengrenzen per zone als % van de drempelsnelheid (zoals [77.5, 87.7, ..., 999]).
    Stilstaan (< 1 m/s) telt niet mee.
    """
    if not threshold_s_km:
        return None
    thr = 1000 / threshold_s_km
    tot = [0.0] * len(pct_bounds)
    for rid in run_ids:
        s = store.streams(rid)
        vel, time = s.get("velocity_smooth") or [], s.get("time") or []
        for i in range(1, min(len(vel), len(time))):
            v, dtm = vel[i], (time[i] or 0) - (time[i - 1] or 0)
            if not v or v < 1.0 or dtm <= 0 or dtm > 30:
                continue
            pct = v / thr * 100
            z = next((k for k, b in enumerate(pct_bounds) if pct <= b), len(pct_bounds) - 1)
            tot[z] += dtm
    return tot


def run_detail(activity_id):
    """Streams (gedownsampled) + splits voor het detailpaneel."""
    s = store.streams(activity_id)
    n = len(s.get("time") or [])
    step = max(1, n // 600)
    pick = lambda k: (s.get(k) or [])[::step]
    vel = pick("velocity_smooth")
    return {
        "time": pick("time"), "distance": [round((d or 0) / 1000, 3) for d in pick("distance")],
        "pace": [round(1000 / v) if v and v > 1.2 else None for v in vel],
        "hr": pick("heartrate"), "cadence": [(c or 0) * 2 or None for c in pick("cadence")],
        "watts": pick("watts"), "altitude": pick("altitude"),
        "splits": splits_per_km(s),
    }


# --------------------------------------------------------------------------- per week
def calibrate(runs):
    """Mediaan verschil tussen race-VDOT en HR-VDOT op runs waar beide bekend zijn."""
    diffs = [r["vdot_race"] - r["vdot_hr"] for r in runs if r["vdot_race"] and r["vdot_hr"]]
    return (statistics.median(diffs), len(diffs)) if len(diffs) >= 2 else (0.0, len(diffs))


WEEK_LISTS = {"ef": "ef", "dec": "decoupling", "cad": "cadence", "stride": "stride", "vo": "vert_osc",
              "vr": "vert_ratio", "gct": "gct", "gctp": "gct_pct", "pw": "power", "effp": "eff_power",
              "rpe": "rpe", "hrr": "hrr60", "tea": "te_aerobic", "tean": "te_anaerobic"}


# Welke zones tellen als rustig / midden / hard
GROUPS = {
    "garmin": ((0, 1, 2), (3,), (4,)),       # Garmin, 5 zones op % max HR: Z1-Z3 / Z4 / Z5
    "model": ((0, 1), (2,), (3, 4)),          # model, 5 zones: herstel+duur / tempo / drempel+VO2max
    "intervals": ((0, 1), (2,), (3, 4, 5, 6)),  # intervals.icu, 7 zones
}


def weekly_runs(runs, offset, groups="intervals"):
    LOW, MID, HIGH = GROUPS[groups]
    weeks = {}
    for r in runs:
        ws = week_start(dt.date.fromisoformat(r["date"])).isoformat()
        w = weeks.setdefault(ws, {"week": ws, "km": 0, "minutes": 0, "runs": 0, "load": 0, "longest": 0,
                                  "elev": 0, "trimp": 0, "race": [], "hr": [], "z": [0] * 7, "pz": [0] * 7,
                                  **{k: [] for k in WEEK_LISTS}})
        w["km"] += r["km"]
        w["minutes"] += r["minutes"]
        w["runs"] += 1
        w["load"] += r["load"] or 0
        w["elev"] += r["elev"] or 0
        w["trimp"] += r["trimp"] or 0
        w["longest"] = max(w["longest"], r["km"])
        if r["vdot_race"]:
            w["race"].append(r["vdot_race"])
        if r["vdot_hr"]:
            w["hr"].append(r["vdot_hr"] + offset)
        for k, key in WEEK_LISTS.items():
            if r.get(key) is not None:
                w[k].append(r[key])
        for i, z in enumerate((r["zones"] or [])[:7]):
            w["z"][i] += z or 0
        w["nz"] = max(w.get("nz", 0), len(r["zones"] or []))
        for i, z in enumerate((r["pace_zones"] or [])[:7]):
            w["pz"][i] += z or 0
    med = lambda xs, nd=3: round(statistics.median(xs), nd) if xs else None
    pct = lambda zs, idx: round(sum(zs[i] for i in idx) / (sum(zs) or 1) * 100) if sum(zs) else None
    out = []
    for ws in sorted(weeks):
        w = weeks[ws]
        vr = max(w["race"]) if w["race"] else None
        vh = statistics.median(w["hr"]) if w["hr"] else None
        use_race = vr and (not vh or vr >= vh - 1.5)
        out.append({
            "week": ws, "km": round(w["km"], 1), "hours": round(w["minutes"] / 60, 2), "runs": w["runs"],
            "load": round(w["load"]), "longest": round(w["longest"], 1), "elev": round(w["elev"]),
            "trimp": round(w["trimp"]),
            "vdot_race": vr, "vdot_hr": round(vh, 2) if vh else None,
            "vdot": vr if use_race else (round(vh, 2) if vh else vr),
            "vdot_src": "race" if use_race else ("hr" if vh else None),
            "ef": med(w["ef"], 4), "decoupling": med(w["dec"], 1), "cadence": med(w["cad"], 1),
            "stride": med(w["stride"]), "vert_osc": med(w["vo"], 2), "vert_ratio": med(w["vr"], 2),
            "gct": med(w["gct"], 1), "gct_pct": med(w["gctp"], 1), "power": med(w["pw"], 0),
            "eff_power": med(w["effp"]), "rpe": med(w["rpe"], 1), "hrr60": med(w["hrr"], 0),
            "te_aerobic": med(w["tea"], 1), "te_anaerobic": med(w["tean"], 1),
            "z7": [pct(w["z"], (i,)) for i in range(w["nz"])] if sum(w["z"]) else None,
            "pz7": [pct(w["pz"], (i,)) for i in range(7)] if sum(w["pz"]) else None,
            "z_low": pct(w["z"], LOW), "z_mid": pct(w["z"], MID), "z_high": pct(w["z"], HIGH),
            "pz_low": pct(w["pz"], (0, 1)), "pz_mid": pct(w["pz"], (2,)), "pz_high": pct(w["pz"], (3, 4, 5, 6)),
        })
    return fill_weeks(out, ["km", "hours", "runs", "load", "elev", "trimp"])


# --------------------------------------------------------------------------- per dag (herstel)
def daily_recovery(wellness, garmin_daily):
    """Eén reeks per dag: intervals-wellness aangevuld met Garmin-dagdata."""
    days = {}
    for w in wellness:
        d = w["id"]
        days[d] = {"date": d, "ctl": w.get("ctl"), "atl": w.get("atl"), "hrv": w.get("hrv"),
                   "rhr": w.get("restingHR"), "sleep_h": round(w["sleepSecs"] / 3600, 2) if w.get("sleepSecs") else None,
                   "sleep_score": w.get("sleepScore"), "steps": w.get("steps"), "vo2max": w.get("vo2max"),
                   "weight": w.get("weight")}
    for d, g in garmin_daily.items():
        row = days.setdefault(d, {"date": d})
        for k in ("readiness", "readiness_level", "readiness_time", "readiness_list", "readiness_morning", "bb_now", "bb_now_time", "bb_high", "bb_low", "bb_charged", "bb_wake", "stress_avg",
                  "hrv_night", "hrv_week", "hrv_status", "hrv_base_lo", "hrv_base_hi", "training_status",
                  "acwr", "load_acute", "load_chronic", "recovery_time_h", "respiration", "intensity_min",
                  "load_focus", "load_aerobic_low", "load_aerobic_high", "load_anaerobic"):
            if g.get(k) is not None:
                row[k] = g[k]
        if g.get("sleep_s"):
            row["sleep_h"] = round(g["sleep_s"] / 3600, 2)
            for k in ("deep", "rem", "light", "awake"):
                if g.get(f"sleep_{k}_s") is not None:
                    row[f"sleep_{k}_h"] = round(g[f"sleep_{k}_s"] / 3600, 2)
        for src, dst in (("sleep_score", "sleep_score"), ("steps", "steps"), ("vo2max", "vo2max"), ("resting_hr", "rhr")):
            if g.get(src) is not None and row.get(dst) is None:
                row[dst] = g[src]
        if row.get("hrv") is None and g.get("hrv_night"):
            row["hrv"] = g["hrv_night"]
    out = sorted(days.values(), key=lambda r: r["date"])
    for r in out:
        if r.get("ctl") is not None:
            r["ctl"] = round(r["ctl"], 1)
            r["atl"] = round(r.get("atl") or 0, 1)
            r["tsb"] = round(r["ctl"] - r["atl"], 1)
    return out


def heat_cells(runs, center, radius_km=10, cell=0.0003):
    """Eigen warmtekaart: per cel (~30 m) het aantal runs dat erdoor kwam, binnen radius_km van center."""
    if not center:
        return []
    counts = {}
    for r in runs:
        s = store.streams(r["id"])
        lat, lng = s.get("lat") or [], s.get("lng") or []
        seen = set()
        for i in range(0, min(len(lat), len(lng)), 3):
            la, lo = lat[i], lng[i]
            if la is None or lo is None:
                continue
            seen.add((round(la / cell), round(lo / cell)))
        for k in seen:
            counts[k] = counts.get(k, 0) + 1
    lat0, lon0 = center
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * math.cos(math.radians(lat0)))
    return [[round(k[0] * cell, 5), round(k[1] * cell, 5), n] for k, n in counts.items()
            if abs(k[0] * cell - lat0) <= dlat and abs(k[1] * cell - lon0) <= dlon]


def build(data):
    """Volledige analyse vanuit de cache."""
    athlete, acts, wellness = data["athlete"], data["activities"], data["wellness"]
    wl = {w["id"]: w for w in wellness}
    run_settings = next((s for s in athlete.get("sportSettings", []) if "Run" in (s.get("types") or [])), {})
    rests = [w["restingHR"] for w in wellness[-30:] if w.get("restingHR")]
    snaps = data.get("garmin_snapshots") or []
    ghz = next((s["hr_zones"] for s in reversed(snaps) if s.get("hr_zones") and s["hr_zones"].get("max")), None)
    ctx = {
        "max_hr": (ghz or {}).get("max") or run_settings.get("max_hr") or 190,
        "lthr": (ghz or {}).get("lthr") or run_settings.get("lthr"),
        "hr_source": "garmin" if ghz else "intervals",
        "hr_floors": [f for f in (ghz or {}).get("floors", []) if f] or None,
        "hr_method": (ghz or {}).get("method"),
        "hr_zones_all": next((s["hr_zones_all"] for s in reversed(snaps) if s.get("hr_zones_all")), None),
        "rest_hr": statistics.median(rests) if rests else 50,
        "tp": run_settings.get("threshold_pace"),
        "wellness": wl, "garmin_acts": data.get("garmin_activities") or [],
        "garmin_extra": data.get("garmin_extra") or {},
    }
    runs = sorted((analyze_run(a, ctx) for a in acts if store.has_data(a) and is_run(a)), key=lambda r: r["date"])
    offset, n_cal = calibrate(runs)
    for r in runs:
        r["vdot_hr_cal"] = round(r["vdot_hr"] + offset, 2) if r["vdot_hr"] else None
    return {
        "ctx": {k: v for k, v in ctx.items() if k not in ("wellness", "garmin_acts", "garmin_extra")},
        "runs": runs, "run_weeks": weekly_runs(runs, offset, "garmin" if ctx.get("hr_floors") else "intervals"),
        "calibration": {"offset": round(offset, 2), "n": n_cal},
        "daily": daily_recovery(wellness, data.get("garmin_daily") or {}),
    }
