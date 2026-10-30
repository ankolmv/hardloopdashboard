"""Trends, voorspelde tijden en scenario's."""
import datetime as dt
import math
import statistics

import metrics as M

MAX_SLOPE = 0.25      # VDOT per week (~1 per maand): realistische bovengrens voor verbetering
HALF_WEEKS = 26.0     # afvlakking: na 26 weken is de verbetering per week gehalveerd
HORIZONS = (4, 8, 12)
RACE_WEIGHT = 2.0     # echte (bijna) maximale inspanningen tellen zwaarder dan HR-schattingen
ANCHOR_WEEKS = 12     # "nu" mag niet lager zijn dan je beste inspanning van de laatste 12 weken...
ANCHOR_DECAY = 0.15   # ...min 0,15 VDOT per week, maar alleen als je sindsdien minder bent gaan trainen


def weighted_linreg(xs, ys, ws):
    sw = sum(ws)
    mx = sum(w * x for x, w in zip(xs, ws)) / sw
    my = sum(w * y for y, w in zip(ys, ws)) / sw
    sxx = sum(w * (x - mx) ** 2 for x, w in zip(xs, ws))
    if sxx == 0:
        return 0.0, my, 0.0, 0.0
    slope = sum(w * (x - mx) * (y - my) for x, y, w in zip(xs, ys, ws)) / sxx
    icpt = my - slope * mx
    n = len(xs)
    resid = [y - (icpt + slope * x) for x, y in zip(xs, ys)]
    sd = math.sqrt(sum(w * r * r for r, w in zip(resid, ws)) / sw * n / max(n - 2, 1)) if n > 2 else 1.5
    se = sd / math.sqrt(sxx / sw * n) if n > 2 else 0.25
    return slope, icpt, sd, se


def recent_best(runs, today, weeks=ANCHOR_WEEKS, decay=ANCHOR_DECAY):
    """Beste maximale inspanning van de laatste weken.

    Rustigere of gedoseerde trainingen zijn geen bewijs dat je vorm achteruitgaat: zolang je evenveel
    blijft trainen, blijft die inspanning gelden. Pas bij minder omvang (km over 4 weken) gaat er
    per week iets af.
    """
    def km_between(a, b):
        return sum(r["km"] for r in runs if a <= dt.date.fromisoformat(r["date"]) < b)

    km_now = km_between(today - dt.timedelta(days=28), today + dt.timedelta(days=1))
    best = None
    for r in runs:
        if not r.get("vdot_race"):
            continue
        d = dt.date.fromisoformat(r["date"])
        age = (today - d).days / 7
        if age > weeks:
            continue
        km_then = km_between(d - dt.timedelta(days=28), d + dt.timedelta(days=1))
        ratio = km_now / km_then if km_then else 1.0
        drop = min(1.0, max(0.0, (0.9 - ratio) / 0.4))  # 90% of meer van de omvang: geen aftrek; 50%: volle aftrek
        v = r["vdot_race"] - decay * age * drop
        if best is None or v > best["value"]:
            best = {"value": v, "vdot": r["vdot_race"], "date": r["date"], "name": r.get("name"), "age_weeks": round(age, 1)}
    return best


def trend(points, today, value_key="vdot", lookback_weeks=26, max_slope=MAX_SLOPE, anchor=None):
    """points: [{"week": iso, value_key: float, "n": weight, "vdot_src": ...}] → fit + projectie-functie.

    anchor: ondergrens voor "nu" (bijv. je beste recente inspanning); de trend bepaalt dan
    alleen nog hoe snel je vanaf dat punt verder verbetert.
    """
    cutoff = today - dt.timedelta(weeks=lookback_weeks)
    pts = [p for p in points if p.get(value_key) is not None and dt.date.fromisoformat(p["week"]) >= cutoff]
    if not pts:
        return None
    t0 = M.week_start(today)
    xs = [(dt.date.fromisoformat(p["week"]) - t0).days / 7 for p in pts]
    ys = [p[value_key] for p in pts]
    ws = [math.exp(x / 12) * (p.get("n") or 1) * (RACE_WEIGHT if p.get("vdot_src") == "race" else 1.0)
          for x, p in zip(xs, pts)]  # recente weken en echte inspanningen zwaarder
    n = len(pts)
    if n >= 3:
        slope, icpt, sd, se = weighted_linreg(xs, ys, ws)
    else:
        slope, icpt, sd, se = 0.0, statistics.mean(ys), 1.5, 0.25
    raw_slope = slope
    if abs(slope) > max_slope:  # begrensde helling: lijn opnieuw door het (gewogen) midden van de punten leggen
        slope = math.copysign(max_slope, slope)
        icpt = sum(w * (y - slope * x) for x, y, w in zip(xs, ys, ws)) / sum(ws)
    fit_now = icpt  # gefitte waarde in de huidige week (x=0)
    now = max(fit_now, anchor) if anchor is not None else fit_now

    def at(h):
        gain = slope * h / (1 + h / HALF_WEEKS)
        band = math.sqrt(sd ** 2 / max(n, 1) + (se * h) ** 2 + (0.15 * h if n < 6 else 0) ** 2)
        return now + gain, band

    span = (max(xs) - min(xs)) if n > 1 else 0
    return {"now": now, "fit_now": fit_now, "anchored": now > fit_now, "slope": slope, "raw_slope": raw_slope, "sd": sd, "n": n, "span_weeks": span,
            "at": at, "fit": [{"week": (t0 + dt.timedelta(weeks=x)).isoformat(), "fit": round(icpt + slope * x, 2)}
                    for x in range(int(min(xs)), 1)]}  # elke week, ook weken zonder punt: een doorlopende lijn


def reliability(n_weeks, n_hard):
    if n_weeks >= 12 and n_hard >= 3:
        return "hoog", "Ruim voldoende data voor een betrouwbare trend."
    if n_weeks >= 6:
        return "redelijk", "Trend is bruikbaar, maar nog gevoelig voor een paar afwijkende weken."
    return "laag", (f"Pas {n_weeks} week/weken met data. Voorspellingen zijn een grove schatting; "
                    "de band wordt smaller naarmate er meer weken bijkomen.")


def _interp(x, pts):
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def endurance_penalty(dist_m, avg_km, longest_km):
    """Extra tijd (fractie) bij weinig omvang: VDOT-tabellen gaan uit van een goede duurbasis.

    Geleidelijk tussen 10 km (geen correctie), halve en hele marathon, zodat ook vrije
    afstanden (bijv. 15 km of 30 km) een passende correctie krijgen.
    """
    km = dist_m / 1000
    w = _interp(km, [(10, 0.0), (21.1, 1.0), (42.2, 1.0)])
    if w == 0:
        return 0.0
    hm = min(1, max(0, (40 - avg_km) / 30)) * 0.03 + min(1, max(0, (16 - longest_km) / 10)) * 0.02
    m = min(1, max(0, (60 - avg_km) / 40)) * 0.08 + min(1, max(0, (28 - longest_km) / 20)) * 0.04
    frac_m = _interp(km, [(21.1, 0.0), (42.2, 1.0)])
    return w * (hm + (m - hm) * frac_m)


def predictions(vdot, band, avg_km, longest_km):
    out = {}
    for k, D in M.RACE_DISTANCES.items():
        pen = endurance_penalty(D, avg_km, longest_km)
        t = M.race_time(vdot, D) * (1 + pen)
        lo = M.race_time(vdot + band, D) * (1 + pen)
        hi = M.race_time(max(vdot - band, 20), D) * (1 + pen)
        out[k] = {"time": t, "lo": lo, "hi": hi, "pace": t / (D / 1000), "penalty": round(pen * 100, 1)}
    return out


def goal_status(dist_m, goal_s, tr, avg_km, longest_km, today):
    """Status van één doel (vrije afstand, geen datum)."""
    pen = endurance_penalty(dist_m, avg_km, longest_km)
    need = M.vdot_from_race(dist_m, goal_s / (1 + pen))
    t_at = lambda v: M.race_time(v, dist_m) * (1 + pen)
    now_v, band = tr["at"](0)
    proj = {}
    for h in (0,) + HORIZONS:
        v, b = tr["at"](h)
        proj[h] = {"vdot": round(v, 2), "time": t_at(v), "lo": t_at(v + b), "hi": t_at(max(v - b, 20))}
    eta_w = next((wk for wk in range(0, 105) if tr["at"](wk)[0] >= need), None)
    # Voortgang: van je eerste gemeten niveau (start trend) naar het doel
    first = tr["fit"][0]["fit"] if tr.get("fit") else now_v
    span = need - first
    progress = 100.0 if now_v >= need else (max(0.0, min(100.0, (now_v - first) / span * 100)) if span > 0 else 0.0)
    gap_s = proj[0]["time"] - goal_s
    if gap_s <= 0:
        status, cls = "Doel binnen bereik", "green"
    elif eta_w is not None and eta_w <= 12:
        status, cls = "Op koers", "green"
    elif eta_w is not None and eta_w <= 26:
        status, cls = "Haalbaar", "orange"
    else:
        status, cls = "Nog ver weg", "red"
    return {"need_vdot": round(need, 1), "now_vdot": round(now_v, 1), "band": round(band, 1),
            "penalty": round(pen * 100, 1), "proj": proj, "gap_s": gap_s, "eta_weeks": eta_w,
            "eta_week": (M.week_start(today) + dt.timedelta(weeks=eta_w)).isoformat() if eta_w is not None else None,
            "progress": round(progress), "status": status, "cls": cls, "start_vdot": round(first, 1)}


def simulate_ctl(ctl0, daily_load, days):
    ctl, out = ctl0, []
    for d in range(1, days + 1):
        ctl += (daily_load - ctl) / 42
        if d % 7 == 0:
            out.append(round(ctl, 1))
    return out


def scenario(weeks, runs, load_series, run_weeks_vdot, km_per_week):
    """Scenario B: belasting vasthouden op km_per_week. CTL vooruit simuleren (Banister)."""
    recent = [r for r in runs if r["load"] and r["km"]][-20:]
    load_per_km = statistics.median(r["load"] / r["km"] for r in recent) if recent else 6.0
    with_ctl = [p for p in load_series if p.get("ctl") is not None]
    ctl0 = with_ctl[-1]["ctl"] if with_ctl else 0
    daily = km_per_week * load_per_km / 7
    ctl = simulate_ctl(ctl0, daily, weeks * 7)
    # Persoonlijke relatie VDOT ~ CTL (alleen met voldoende weken)
    ctl_by_week = {}
    for p in with_ctl:
        ws = M.week_start(dt.date.fromisoformat(p["date"])).isoformat()
        ctl_by_week[ws] = p["ctl"]
    pairs = [(ctl_by_week[w["week"]], w["vdot"]) for w in run_weeks_vdot if w.get("vdot") and w["week"] in ctl_by_week]
    model = None
    if len(pairs) >= 8:
        xs, ys = zip(*pairs)
        if statistics.pstdev(xs) > 2:
            slope, icpt, sd, _ = weighted_linreg(list(xs), list(ys), [1] * len(xs))
            if slope > 0:
                model = {"slope": slope, "icpt": icpt, "sd": sd}
    vdot_proj = [round(model["icpt"] + model["slope"] * c, 2) for c in ctl] if model else None
    return {"km_per_week": km_per_week, "load_per_km": round(load_per_km, 2), "ctl_now": ctl0,
            "ctl": ctl, "vdot": vdot_proj, "model": model, "n_pairs": len(pairs)}
