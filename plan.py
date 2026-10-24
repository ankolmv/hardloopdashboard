"""Trainingsplan: fase, weekomvang, indeling over je trainingsdagen, uitleg, volgende week en bijsturen.

Werkt met het doel uit goal.json:
  {"type": "event"|"general", "distance_km": 10, "time": "45:00" (optioneel), "date": "2027-03-14" (event), "name": ...}
en de instellingen: run_days (bijv. [1, 3, 5, 6]), long_days ([4, 5, 6]) en plan_start (begin van de 4-weekse cyclus).

Trainingen hebben hetzelfde formaat als het dagvoorstel (analysis.suggest), zodat ze ook naar Garmin kunnen.
"""
import datetime as dt
import itertools
import math
import statistics

import analysis as AN
import metrics as M

DAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
DAYS_SHORT = ["ma", "di", "wo", "do", "vr", "za", "zo"]
PHASE_LABELS = {"basis": "Basis", "opbouw": "Opbouw", "specifiek": "Specifiek", "taper": "Taper",
                "race": "Wedstrijdweek", "herstel": "Herstelweek"}
KIND_LABELS = {"rust": "Rust", "rustig": "Rustige duurloop", "lang": "Lange duurloop", "drempel": "Drempeltraining",
               "interval": "Intervaltraining", "wedstrijdtempo": "Wedstrijdtempo", "herstel": "Herstelrun",
               "wedstrijd": "Wedstrijd", "anaeroob": "Snelheid (anaeroob)"}
QUALITY = ("drempel", "interval", "wedstrijdtempo", "anaeroob")


# --------------------------------------------------------------------------- hulpfuncties
def _taper_weeks(km):
    return 1 if km <= 10.5 else 2 if km <= 25 else 3


def _long_cap(km):
    return 14 if km <= 5.5 else 18 if km <= 10.5 else 22 if km <= 25 else 32


def _cdist(a, b):
    """Afstand in dagen. Dagen van de vorige week tellen als -7..-1 (zondag ervoor = -1)."""
    return abs(a - b)


def _fmt_km(x):
    return (f"{x:.1f}".rstrip("0").rstrip(".")).replace(".", ",")


def phase_for(goal, settings, week_start):
    """Fase van een week, plus info voor de uitleg."""
    km = (goal or {}).get("distance_km") or 10
    start = dt.date.fromisoformat(settings.get("plan_start") or week_start.isoformat())
    cycle_idx = max(0, (week_start - M.week_start(start)).days // 7)
    info = {"cycle_week": cycle_idx % 4 + 1, "weeks_to": None}
    if goal and goal.get("type") == "event" and goal.get("date"):
        race = dt.date.fromisoformat(goal["date"])
        wt = (M.week_start(race) - week_start).days // 7
        info["weeks_to"] = wt
        tw = _taper_weeks(km)
        if wt < 0:
            phase = "herstel"
        elif wt == 0:
            phase = "race"
        elif wt <= tw:
            phase = "taper"
        elif wt <= tw + 4:
            phase = "specifiek"
        elif wt <= 16:
            phase = "opbouw"
        else:
            phase = "basis"
        info["taper_index"] = tw - wt + 1 if phase == "taper" else None
    else:
        phase = "opbouw"
    info["recovery"] = phase in ("basis", "opbouw") and cycle_idx % 4 == 3
    return phase, info


def _session(kind, km_target, ctx, label_extra=None, variant=0):
    """Training in stappen (zelfde formaat als analysis.suggest). km_target alleen voor rustig/lang/herstel."""
    z, paces, goal_km, phase = ctx["z"], ctx["paces"], ctx["goal_km"], ctx["phase"]
    e_mid = (paces["E_fast"] + paces["E_slow"]) / 2
    hr2 = [z[1][0], z[1][1]]
    if kind in ("rustig", "herstel"):
        secs = max(20, round(km_target * e_mid / 60 / 5) * 5) * 60
        steps = [{"kind": "run", "secs": secs, "hr": hr2, "pace": [paces["E_fast"], paces["E_slow"]],
                  "label": "Rustig in Z2" if kind == "rustig" else "Rustig in Z2 (onderste helft)"}]
        if label_extra == "strides":
            steps[0]["secs"] = max(1200, secs - 360)
            steps += [{"kind": "repeat", "n": 6, "steps": [{"kind": "interval", "secs": 20, "label": "Versnelling (snel, ontspannen)"},
                                                           {"kind": "recovery", "secs": 40, "label": "Dribbelen"}]}]
        title = f"{KIND_LABELS[kind]} {round(secs / 60)} min" + (" + versnellingen" if label_extra == "strides" else "")
        return title, steps
    if kind == "lang":
        secs = round(km_target * e_mid / 60 / 5) * 5 * 60
        steps = [{"kind": "warmup", "secs": 600, "hr": hr2, "label": "Inlopen"}]
        if label_extra == "finish" and goal_km >= 15:  # halve/hele marathon: laatste stuk op wedstrijdtempo
            fin = 20 * 60 if goal_km < 30 else 30 * 60
            rp = ctx["race_pace"]
            steps += [{"kind": "run", "secs": max(600, secs - 600 - fin), "hr": hr2, "pace": [paces["E_fast"], paces["E_slow"]], "label": "Rustig in Z2"},
                      {"kind": "interval", "secs": fin, "pace": [rp - 5, rp + 5], "label": "Wedstrijdtempo"}]
        else:
            steps += [{"kind": "run", "secs": max(600, secs - 600), "hr": hr2, "pace": [paces["E_fast"], paces["E_slow"]], "label": "Rustig in Z2"}]
        return f"Lange duurloop {_fmt_km(km_target)} km", steps
    wu = {"kind": "warmup", "secs": 900, "hr": hr2, "label": "Inlopen"}
    cd = {"kind": "cooldown", "secs": 600, "label": "Uitlopen"}
    if kind == "drempel":
        if phase == "basis":
            reps, mins = 3, 6
        elif phase in ("taper", "race"):
            reps, mins = 2, 6
        else:  # opbouw/specifiek: afwisselend 3×10, 4×8, 2×15
            reps, mins = [(3, 10), (4, 8), (2, 15)][variant % 3]
        steps = [wu, {"kind": "repeat", "n": reps, "steps": [
            {"kind": "interval", "secs": mins * 60, "pace": [paces["T"] - 5, paces["T"] + 5], "hr": [z[3][0], z[3][1]], "label": "Drempeltempo"},
            {"kind": "recovery", "secs": 120, "label": "Dribbelen"}]}, cd]
        return f"Drempeltraining {reps}× {mins} min", steps
    if kind == "interval":
        if phase in ("taper", "race"):
            reps, secs = 4, 120
        else:
            reps, secs = [(5, 180), (4, 240), (6, 150)][variant % 3]
        steps = [wu, {"kind": "repeat", "n": reps, "steps": [
            {"kind": "interval", "secs": secs, "pace": [paces["I"] - 5, paces["I"] + 5], "label": "Interval"},
            {"kind": "recovery", "secs": max(90, int(secs * 0.8)), "label": "Dribbelen"}]}, cd]
        return f"Intervaltraining {reps}× {secs // 60 if secs % 60 == 0 else round(secs / 60, 1)} min".replace(".", ","), steps
    if kind == "anaeroob":  # korte, bijna maximale stukken met ruim herstel: anaerobe capaciteit en snelheid
        reps, secs = [(8, 30), (10, 30), (6, 45)][variant % 3]
        fast = paces.get("R") or paces["I"] - 15
        steps = [wu, {"kind": "repeat", "n": reps, "steps": [
            {"kind": "interval", "secs": secs, "pace": [fast - 35, fast - 10], "label": "Snel (±90–95% van je max), ontspannen blijven"},
            {"kind": "recovery", "secs": 120, "label": "Wandelen/dribbelen"}]}, cd]
        return f"Snelheid {reps}× {secs} s", steps
    if kind == "wedstrijdtempo":
        rp = ctx["race_pace"]
        if goal_km <= 10.5:
            reps, work = (5, 1000) if phase != "taper" else (3, 1000)
            secs = round(work / 1000 * rp)
            steps = [wu, {"kind": "repeat", "n": reps, "steps": [
                {"kind": "interval", "secs": secs, "pace": [rp - 4, rp + 4], "label": f"{work} m op wedstrijdtempo"},
                {"kind": "recovery", "secs": 120, "label": "Dribbelen"}]}, cd]
            return f"Wedstrijdtempo {reps}× {work} m", steps
        reps, mins = (2, 15) if goal_km < 30 else (2, 25)
        steps = [wu, {"kind": "repeat", "n": reps, "steps": [
            {"kind": "interval", "secs": mins * 60, "pace": [rp - 5, rp + 5], "label": "Wedstrijdtempo"},
            {"kind": "recovery", "secs": 180, "label": "Dribbelen"}]}, cd]
        return f"Wedstrijdtempo {reps}× {mins} min", steps
    raise ValueError(kind)


def _secs(steps):
    return sum(s["secs"] if s["kind"] != "repeat" else s["n"] * _secs(s["steps"]) for s in steps)


def _km(steps, paces):
    """Geschatte afstand: stappen met tempo op dat tempo, de rest op rustig tempo."""
    e_mid = (paces["E_fast"] + paces["E_slow"]) / 2
    tot = 0.0
    for s in steps:
        if s["kind"] == "repeat":
            tot += s["n"] * _km(s["steps"], paces)
        else:
            p = statistics.mean(s["pace"]) if s.get("pace") else (e_mid + 60 if s["kind"] == "recovery" else e_mid)
            tot += s["secs"] / p
    return tot


# --------------------------------------------------------------------------- uitleg
PURPOSE = {
    "rustig": "Rustige kilometers in Z2 bouwen je aerobe basis (meer haarvaten en mitochondriën) en maken je zuiniger, zonder veel vermoeidheid.",
    "lang": "De lange duurloop traint je uithoudingsvermogen en vetverbranding, en maakt pezen en spieren sterker voor langere afstanden.",
    "drempel": "Drempeltraining verhoogt het tempo dat je lang kunt volhouden. Dat is de belangrijkste factor voor 10 km tot halve marathon.",
    "interval": "Intervallen van 2–4 min op VO2max-tempo vergroten je 'motor' (maximale zuurstofopname) en je snelheid.",
    "wedstrijdtempo": "Op wedstrijdtempo lopen leert je lichaam en hoofd precies dat tempo; je pacing wordt beter en het voelt op de dag vertrouwd.",
    "herstel": "Een korte, rustige run bevordert de doorbloeding en het herstel zonder nieuwe vermoeidheid.",
    "wedstrijd": "Wedstrijddag: alles komt samen.",
    "anaeroob": "Korte, bijna maximale stukken met ruim herstel trainen je anaerobe capaciteit, snelheid en loopeconomie; zo kun je versnellen en een eindsprint plaatsen.",
    "rust": "Rust is waar je lichaam sterker wordt van de training die je deed.",
}
FOCUS = {
    "basis": "aerobe basis en belastbaarheid opbouwen: vooral rustige kilometers, lichte prikkels",
    "opbouw": "fitheid en snelheid opbouwen: twee kwaliteitstrainingen per week naast rustige kilometers",
    "specifiek": "wedstrijdspecifiek: trainen op en rond je doeltempo",
    "taper": "fris worden voor de wedstrijd: minder kilometers, kort en scherp blijven",
    "race": "wedstrijdweek: weinig en rustig, met een korte opfrisser",
    "herstel": "herstel na de wedstrijd",
}


def _placement_why(day, kind, days_plan):
    """Waarom staat deze training op deze dag?"""
    others = {d: k for d, k in days_plan.items() if d != day and k not in ("rust",)}
    hard = [d for d, k in others.items() if k in QUALITY or k == "lang"]
    if kind in QUALITY:
        gaps = sorted(_cdist(day, d) for d in hard) or [7]
        before_long = [d for d, k in others.items() if k == "lang"]
        txt = f"Op {DAYS[day]}: " + (f"minstens {gaps[0]} dag(en) tussen de andere zware trainingen" if gaps[0] >= 2
                                     else "zo ver mogelijk van de andere zware trainingen met jouw trainingsdagen")
        if before_long and _cdist(day, before_long[0]) == 1:
            txt += " (let op: dag naast de lange run, houd het tempo beheerst)"
        return txt + "."
    if kind == "lang":
        return f"Op {DAYS[day]}: je lange run valt in het weekend (vrijdag–zondag), wanneer je er de tijd voor hebt."
    if kind == "rustig":
        if day - 1 in hard:
            return (f"Op {DAYS[day]}: rustig, om te herstellen van de zware training van gisteren"
                    + (" (zondag, vorige week)." if day == 0 else "."))
        if day + 1 in hard:
            return f"Op {DAYS[day]}: rustig, zodat je fris bent voor de zware training van morgen."
        return f"Op {DAYS[day]}: rustig tussen de zware trainingen door; dat houdt de week in balans."
    return ""


# --------------------------------------------------------------------------- weekplan
def week_run_days(settings, week_start):
    """Trainingsdagen voor een week: per week aangepast, anders je vaste dagen."""
    custom = (settings.get("week_days") or {}).get(week_start.isoformat())
    return sorted(set(custom if custom else settings.get("run_days") or [1, 3, 5, 6])), bool(custom)


def plan_week(week_start, base_km, longest_km, goal, settings, ctx, prev_target=None, is_next=False, done=None, prev_hard=None):
    """Weekplan. `done` = {weekdag: [runs]} voor dagen die al voorbij zijn (of vandaag al gelopen):
    die liggen vast, de rest van de week wordt daarop afgestemd.
    `prev_hard` = {weekdag: soort} met de zware dagen van de week ervoor, zodat bijv. na een zware zondag
    de maandag rustig blijft."""
    run_days, custom_days = week_run_days(settings, week_start)
    long_days = settings.get("long_days") or [4, 5, 6]
    goal_km = (goal or {}).get("distance_km") or 10
    phase, pinfo = phase_for(goal, settings, week_start)
    recovery = pinfo["recovery"]
    n = len(run_days)
    done = done or {}
    closed = set(done)  # dagen die vastliggen

    # ---- weekomvang
    ref = prev_target if prev_target else base_km
    if phase == "race":
        target = base_km * 0.45
    elif phase == "taper":
        target = base_km * [0.7, 0.6, 0.5][min(2, (pinfo.get("taper_index") or 1) - 1)]
    elif phase == "herstel":
        target = base_km * 0.5
    elif recovery:
        target = base_km * 0.75
    else:
        target = ref * 1.07 if prev_target else base_km * 1.07
        target = min(target, (ctx["max_recent_km"] if not prev_target else prev_target) * 1.10)
    target = max(target, n * 4.0)

    # ---- wat is er al gedaan?
    done_kind = {d: _main_kind(rs) for d, rs in done.items() if rs}
    # kwaliteit gedaan = een zware run die geen lange duurloop is
    done_hard = [d for d, rs in done.items() if done_kind.get(d) in QUALITY
                 or (done_kind.get(d) not in ("lang",) and any(AN.is_hard(r) for r in rs))]
    done_q_kinds = [done_kind[d] for d in done_hard if done_kind.get(d) in QUALITY]
    long_done = any(k == "lang" for k in done_kind.values())
    done_km = sum(r["km"] for rs in done.values() for r in rs)
    prev_hard = prev_hard or {}
    fixed_hard = sorted(set(done_hard) | {d for d, k in done_kind.items() if k == "lang"} | {d - 7 for d in prev_hard})

    # ---- dagen kiezen voor de rest van de week
    open_days = [d for d in run_days if d not in closed]
    n_q = 0 if phase == "herstel" else 1 if (n <= 3 or recovery or phase in ("taper", "race", "basis")) else 2
    bal = ctx.get("balance_focus") or {}
    if bal.get("low") == "short" and n_q == 2 and phase in ("basis", "opbouw"):
        n_q = 1  # te weinig rustige basis: één kwaliteitstraining minder, meer rustige kilometers
    n_q_left = max(0, n_q - len(done_hard))
    if long_done:
        cand_long = [None]
    else:
        cand_long = [d for d in (6, 5, 4) if d in open_days and d in long_days] or ([open_days[-1]] if open_days else [None])

    # Alle combinaties (lange-run-dag + kwaliteitsdagen) bekijken: zo veel mogelijk rust tussen álle zware trainingen,
    # ook de trainingen die je al gedaan hebt. Lukt dat niet met een dag ertussen, dan liever een kwaliteitstraining minder.
    def spread(ld, combo):
        hard = tuple(fixed_hard) + ((ld,) if ld is not None else ()) + combo
        gaps = [_cdist(a, b) for a, b in itertools.combinations(hard, 2)] or [7]
        new = [x for x in ((ld,) if ld is not None else ()) + combo]
        new_gaps = [_cdist(a, b) for a in new for b in hard if a != b] or [7]
        return (min(new_gaps), min(gaps), sum(gaps), -cand_long.index(ld), -sum(combo))

    q_dropped = False
    long_day, combo = cand_long[0], ()
    for k in range(n_q_left, -1, -1):
        options = [(ld, c) for ld in cand_long for c in itertools.combinations([d for d in open_days if d != ld], k)]
        if not options:
            continue
        long_day, combo = max(options, key=lambda o: spread(*o))
        qgap = min([_cdist(q, h) for q in combo for h in tuple(fixed_hard) + ((long_day,) if long_day is not None else ()) + combo if q != h] or [7])
        if qgap >= 2 or k == 0:
            break
        q_dropped = True
    q_days = sorted(combo)

    # ---- soorten kwaliteit (wat je al deed eerst wegstrepen)
    if phase == "basis":
        q_kinds = ["drempel"]
    elif phase == "specifiek":
        q_kinds = ["wedstrijdtempo", "interval" if goal_km <= 10.5 else "drempel"]
    elif phase in ("taper", "race"):
        q_kinds = ["wedstrijdtempo" if goal_km <= 10.5 else "drempel"]
    else:
        q_kinds = ["interval", "drempel"] if goal_km <= 10.5 else ["drempel", "interval" if goal_km <= 25 else "wedstrijdtempo"]
    # Garmins trainingsbalans (4 weken): tekorten aanvullen, overschot afbouwen (niet in de specifieke fase/taper)
    focus = ctx.get("balance_focus") or {}
    bal_note = None
    if phase in ("basis", "opbouw", "herstel") or recovery:
        if focus.get("ana") == "short" and n_q >= 1:
            q_kinds = ["anaeroob"] + [k for k in q_kinds if k != "interval"][:1] if focus.get("high") == "over" else ["anaeroob"] + q_kinds[1:]
            bal_note = "anaeroob"
        elif focus.get("high") == "short" and "drempel" not in q_kinds:
            q_kinds = ["drempel"] + q_kinds[1:]
            bal_note = "high_short"
    todo = list(q_kinds)
    for k in done_q_kinds:
        if k in todo:
            todo.remove(k)
    todo = todo or list(q_kinds)
    variant = pinfo["cycle_week"] - 1

    days_plan = {d: "rust" for d in range(7) if d not in closed}
    for d in open_days:
        days_plan[d] = "rustig"
    if long_day is not None:
        days_plan[long_day] = "lang"
    for i, d in enumerate(q_days):
        days_plan[d] = todo[i % len(todo)]
    if phase == "race" and goal and goal.get("date"):
        race_day = dt.date.fromisoformat(goal["date"]).weekday()
        if race_day not in closed:
            days_plan[race_day] = "wedstrijd"
            for d in range(race_day + 1, 7):
                days_plan[d] = "rust"
            if long_day is not None and long_day != race_day and days_plan.get(long_day) == "lang":
                days_plan[long_day] = "rustig" if long_day < race_day - 1 else "rust"

    # ---- sessies bouwen
    sessions = {}
    long_km = min(_long_cap(goal_km), max(6.0, target * (0.38 if n <= 3 else 0.30 if goal_km <= 10.5 else 0.35)),
                  (longest_km or 8) * 1.10 + 1)
    if phase in ("taper", "race"):
        long_km = min(long_km, _long_cap(goal_km) * 0.65)
    for d, k in days_plan.items():
        if k in QUALITY:
            title, steps = _session(k, None, ctx, variant=variant + d)
            sessions[d] = (k, title, steps)
        elif k == "lang":
            title, steps = _session("lang", long_km, ctx, "finish" if phase == "specifiek" else None)
            sessions[d] = (k, title, steps)
        elif k == "wedstrijd":
            km = goal_km
            sessions[d] = (k, f"Wedstrijd: {goal.get('name') or _fmt_km(km) + ' km'}",
                           [{"kind": "warmup", "secs": 900, "label": "Inlopen + 4 versnellingen"},
                            {"kind": "interval", "secs": round(km * ctx["race_pace"]), "pace": [ctx["race_pace"] - 3, ctx["race_pace"] + 3], "label": "Wedstrijd"}])
    used = sum(_km(sv[2], ctx["paces"]) for sv in sessions.values())
    easy_days = [d for d, k in days_plan.items() if k == "rustig"]
    if easy_days:
        each = max(5.0, min(long_km * 0.75, (target - done_km - used) / len(easy_days)))
        if phase == "race":
            each = min(each, 5.0)
        # versnellingen bij de rustige run die het verst van zware dagen ligt
        hard = [d for d, k in days_plan.items() if k in QUALITY or k in ("lang", "wedstrijd")] + fixed_hard
        strides = max(easy_days, key=lambda d: min((_cdist(d, h) for h in hard), default=7)) if phase != "herstel" else None
        for d in easy_days:
            title, steps = _session("rustig", each, ctx, "strides" if d == strides else None)
            sessions[d] = ("rustig", title, steps)

    all_kinds = {**{d - 7: k for d, k in prev_hard.items()}, **days_plan, **done_kind}
    days = []
    for d in range(7):
        date = week_start + dt.timedelta(days=d)
        base = {"date": date.isoformat(), "weekday": DAYS[d], "dow": d}
        if d in done:
            rs = done[d]
            k = done_kind.get(d, "rust")
            if rs:
                main = max(rs, key=lambda r: r["km"])
                days.append({**base, "kind": k, "title": AN.TYPE_LABELS.get(k, k), "steps": [],
                             "minutes": round(sum(r["minutes"] for r in rs)), "km": round(sum(r["km"] for r in rs), 1),
                             "status": "done" if d in run_days else "extra", "hard": d in done_hard,
                             "actual": {"km": round(sum(r["km"] for r in rs), 1), "name": main["name"], "kind": k,
                                        "kind_label": AN.TYPE_LABELS.get(k, k)},
                             "why": []})
            else:
                days.append({**base, "kind": "rust", "title": "Rust", "steps": [], "minutes": 0, "km": 0, "status": "rest", "why": []})
        elif d in sessions:
            k, title, steps = sessions[d]
            days.append({**base, "kind": k, "title": title, "steps": steps,
                         "minutes": round(_secs(steps) / 60), "km": round(_km(steps, ctx["paces"]), 1),
                         "why": [PURPOSE.get(k, ""), _placement_why(d, k, all_kinds)]})
        else:
            days.append({**base, "kind": "rust", "title": "Rust", "steps": [], "minutes": 0, "km": 0,
                         "why": [PURPOSE["rust"]] if d not in run_days else []})

    planned_km = sum(x["km"] for x in days)
    q_min = sum(x["minutes"] for x in days if x["kind"] in QUALITY)
    tot_min = sum(x["minutes"] for x in days) or 1
    hard_share = round(q_min * 0.45 / tot_min * 100)  # ±45% van een kwaliteitstraining is echt hard (rest = in/uitlopen)
    lab, rng = M.week_label(week_start)
    week = {"start": week_start.isoformat(), "label": lab, "range": rng, "phase": "herstel" if recovery and phase in ("basis", "opbouw") else phase,
            "phase_label": PHASE_LABELS["herstel" if recovery and phase in ("basis", "opbouw") else phase],
            "cycle_week": pinfo["cycle_week"], "weeks_to": pinfo["weeks_to"], "target_km": round(target, 1),
            "planned_km": round(planned_km, 1), "base_km": round(base_km, 1), "days": days,
            "sessions": sum(1 for x in days if x["kind"] != "rust"), "quality": len([x for x in days if x["kind"] in QUALITY]),
            "easy_pct": 100 - hard_share, "q_dropped": q_dropped, "balance": ctx.get("balance_text") if (phase in ("basis", "opbouw", "herstel") or recovery) else None, "run_days": run_days, "custom_days": custom_days,
            "done": {"km": round(done_km, 1), "quality": len(done_hard), "long": long_done, "q_left": len(q_days),
                     "long_left": long_day is not None and days_plan.get(long_day) == "lang"} if done else None}
    week["why"] = _week_why(week, phase, pinfo, recovery, goal, base_km, prev_target, is_next)
    return week


def _main_kind(rs):
    """Soort training van een dag: de zwaarste run telt (kwaliteit > lang > rustig)."""
    kinds = [AN.classify(r) for r in rs]
    for k in ("interval", "drempel", "wedstrijdtempo", "lang"):
        if k in kinds:
            return k
    return kinds[-1] if kinds else "rust"


def _week_why(w, phase, pinfo, recovery, goal, base_km, prev_target, is_next):
    gkm = (goal or {}).get("distance_km") or 10
    gname = (goal or {}).get("name") or f"{_fmt_km(gkm)} km"
    out = []
    if goal and goal.get("type") == "event" and pinfo["weeks_to"] is not None and pinfo["weeks_to"] >= 0:
        wt, gd = pinfo["weeks_to"], dt.date.fromisoformat(goal["date"])
        when = "Deze week" if wt == 0 else f"Nog {wt} {'week' if wt == 1 else 'weken'} tot"
        out.append(f"{when} {gname} ({gd.day} {M.MONTHS[gd.month - 1]}). Fase: {PHASE_LABELS[phase].lower()} — {FOCUS[phase]}.")
    else:
        out.append(f"Doel: sneller op de {gname}. Je zit in een cyclus van 4 weken (3 weken opbouw, 1 week herstel); "
                   f"dit is week {pinfo['cycle_week']} van 4. Focus: {FOCUS['opbouw' if not recovery else 'basis']}.")
    ref = prev_target or base_km
    if recovery:
        out.append(f"Herstelweek: ±{_fmt_km(w['target_km'])} km (−25% t.o.v. je gemiddelde van {_fmt_km(base_km)} km). "
                   f"Je lichaam wordt sterker in de rust ná de opbouw; zonder herstelweek stapelt vermoeidheid zich op.")
    elif phase in ("taper", "race"):
        out.append(f"Minder kilometers (±{_fmt_km(w['target_km'])} km) zodat je fris aan de start staat; de korte, snelle blokken houden je scherp.")
    else:
        pct = round((w["target_km"] / ref - 1) * 100) if ref else 0
        out.append(f"Doel ±{_fmt_km(w['target_km'])} km: {'+' if pct >= 0 else ''}{pct}% t.o.v. "
                   + (f"deze week ({_fmt_km(ref)} km)" if prev_target else f"je gemiddelde van de laatste 4 weken ({_fmt_km(base_km)} km)")
                   + ". Max ~10% per week erbij voorkomt blessures.")
    out.append(f"{w['sessions']} trainingen, waarvan {w['quality']} kwaliteit; ±{w['easy_pct']}% van je looptijd is rustig. "
               f"Sterke duurlopers trainen ±80% rustig: de rustige runs maken de harde mogelijk.")
    dn = w.get("done")
    if dn:
        left = []
        if dn["q_left"]:
            left.append(f"nog {dn['q_left']} kwaliteitstraining{'en' if dn['q_left'] > 1 else ''}")
        if dn["long_left"]:
            left.append("de lange duurloop")
        out.append(f"Al gedaan deze week: {_fmt_km(dn['km'])} km, {dn['quality']} zware training{'en' if dn['quality'] != 1 else ''}"
                   + (", lange duurloop ✓" if dn["long"] else "") + ". De rest van de week is daarop afgestemd"
                   + (f": {' en '.join(left)}, met een rustige dag naast elke zware training." if left else ": alleen nog rustige kilometers."))
    if w.get("balance"):
        out.append(w["balance"])
    if w.get("custom_days"):
        out.append("Je hebt voor deze week andere trainingsdagen gekozen dan normaal.")
    if w.get("q_dropped"):
        out.append("Met jouw trainingsdagen passen twee kwaliteitstrainingen niet zonder twee zware dagen achter elkaar; "
                   "daarom deze week één. Wil je er twee, kies dan dagen met telkens een dag ertussen.")
    keys = {x["kind"] for x in w["days"]}
    if "interval" in keys and "drempel" in keys:
        out.append("Kerntrainingen: intervallen (VO2max, je motor) en drempel (het tempo dat je lang volhoudt) — samen de basis voor een snellere " + gname + ".")
    elif "wedstrijdtempo" in keys:
        out.append("Kerntraining: wedstrijdtempo, zodat je doeltempo vertrouwd voelt.")
    elif "drempel" in keys:
        out.append("Kerntraining: drempel — het tempo dat je lang kunt volhouden omhoog.")
    if is_next:
        out.append("Dit is een vooruitblik: het plan wordt elke dag opnieuw berekend met wat je echt gelopen hebt en je herstel.")
    return out


# --------------------------------------------------------------------------- deze week bijsturen
def free_slot(week, d, counts=lambda x: True, statuses=("planned",)):
    """Eerstvolgende rustige dag na `d` in dezelfde week, met minstens 1 dag rust tot de andere zware trainingen."""
    hard_days = [x["dow"] for x in week["days"] if x["kind"] in QUALITY + ("lang",) and x is not d and counts(x)]
    future = [x for x in week["days"] if x["dow"] > d["dow"] and x.get("status", "planned") in statuses
              and x["kind"] == "rustig" and all(_cdist(x["dow"], h) >= 2 for h in hard_days)]
    return future[0] if future else None



# --------------------------------------------------------------------------- hoofdingang
def build(runs, run_weeks, daily_by, zones, paces, vdot, today, goal, settings, balance=None):
    if not (paces and zones and runs):
        return None
    goal = goal or {"type": "general", "distance_km": 10}
    this_ws = M.week_start(today)
    settings = {**settings, "plan_start": settings.get("plan_start") or this_ws.isoformat()}
    auto_days = not settings.get("run_days")
    if auto_days:
        settings["run_days"] = habitual_days(runs, today, settings.get("long_days") or [4, 5, 6])
    goal_km = goal.get("distance_km") or 10
    z = {i: (zn["from"] or 100, zn["to"]) for i, zn in enumerate(zones)}
    rp = M.race_time(vdot, goal_km * 1000) / goal_km if vdot else paces["T"]
    if goal.get("time"):  # doeltijd: train op het doeltempo, maar niet harder dan 3% boven je huidige niveau
        gs = AN_parse(goal["time"])
        if gs:
            rp = max(gs / goal_km, rp * 0.97)
    done = [w for w in run_weeks if w["week"] < this_ws.isoformat()][-4:]
    base_km = statistics.mean(w["km"] for w in done) if done else 15.0
    max_recent = max([w["km"] for w in done] or [base_km])
    longest = max([r["km"] for r in runs if (today - dt.date.fromisoformat(r["date"])).days <= 28] or [8])
    ctx = {"z": z, "paces": paces, "goal_km": goal_km, "race_pace": rp, "max_recent_km": max_recent, "phase": None}
    ctx.update(_balance_ctx(balance))

    def week(ws, prev_target=None, is_next=False, done=None, prev_hard=None):
        ctx["phase"] = phase_for(goal, settings, ws)[0]
        return plan_week(ws, base_km, longest, goal, settings, ctx, prev_target, is_next, done, prev_hard)

    # Zware dagen van vorige week (echt gelopen), zodat deze week daarop aansluit
    last_ws = this_ws - dt.timedelta(weeks=1)
    hard_last = {}
    for d in range(7):
        rs = [r for r in runs if r["date"] == (last_ws + dt.timedelta(days=d)).isoformat()]
        k = _main_kind(rs) if rs else None
        if k in QUALITY + ("lang",) or any(AN.is_hard(r) for r in rs):
            hard_last[d] = k

    # Wat er deze week al gebeurd is: dagen vóór vandaag liggen vast, vandaag ook als je al gelopen hebt
    ran_today = any(r["date"] == today.isoformat() for r in runs)
    done = {}
    for d in range(today.weekday() + (1 if ran_today else 0)):
        date = (this_ws + dt.timedelta(days=d)).isoformat()
        done[d] = [r for r in runs if r["date"] == date]
    orig = week(this_ws, prev_hard=hard_last)  # het plan zoals het aan het begin van de week was (voor 'gemist')
    w1 = week(this_ws, done=done, prev_hard=hard_last)
    for d, o in zip(w1["days"], orig["days"]):
        if d["dow"] in done and o["kind"] != "rust":
            if d["status"] == "rest":  # geplande training niet gelopen
                d.update({"status": "missed", "kind": o["kind"], "title": o["title"], "steps": o["steps"],
                          "minutes": o["minutes"], "km": o["km"], "why": [],
                          "note": "Niet gelopen; de rest van de week is hierop aangepast."})
    for d in w1["days"]:
        if d["dow"] not in done:
            d["status"] = ("today" if d["date"] == today.isoformat() else "planned") if d["kind"] != "rust" else "rest"
    hard_this = {d["dow"]: d["kind"] for d in w1["days"] if d.get("status") != "missed"
                 and (d["kind"] in QUALITY + ("lang", "wedstrijd") or d.get("hard"))}
    w2 = week(this_ws + dt.timedelta(weeks=1), prev_target=w1["target_km"] if w1["phase"] not in ("herstel", "taper", "race") else None,
              is_next=True, prev_hard=hard_this)
    if w1["phase"] != w2["phase"]:
        w2["why"].insert(1, f"Volgende week verandert de fase: {w1['phase_label'].lower()} → {w2['phase_label'].lower()}.")
    timeline = None
    if goal.get("type") == "event" and goal.get("date"):
        race = dt.date.fromisoformat(goal["date"])
        weeks = max(0, (M.week_start(race) - this_ws).days // 7)
        timeline = [{"label": M.week_label(this_ws + dt.timedelta(weeks=i))[0],
                     "phase": phase_for(goal, settings, this_ws + dt.timedelta(weeks=i))[0]} for i in range(min(weeks + 1, 30))]
    return {"goal": goal, "this_week": w1, "next_week": w2, "timeline": timeline,
            "run_days": settings["run_days"], "run_days_auto": auto_days, "long_days": settings.get("long_days") or [4, 5, 6]}


def _balance_ctx(balance):
    """Garmins trainingsbalans vertalen naar bijsturing + uitleg voor het weekplan."""
    if not balance or not balance.get("cats"):
        return {}
    c = balance["cats"]
    focus = {k: v["status"] for k, v in c.items() if v.get("status")}
    fmt = lambda k: f"{c[k]['value']}, doel {c[k]['min']}–{c[k]['max']}"
    parts = []
    if focus.get("ana") == "short":
        parts.append(f"tekort aan anaeroob ({fmt('ana')}): er staat een snelheidstraining met korte, bijna maximale stukken in")
    if focus.get("high") == "over":
        parts.append(f"te veel hoog aeroob ({fmt('high')}): minder drempel/VO2max, en houd je rustige runs écht in Z2 (onder "
                     "je Z3-grens), want 'rustig maar net te snel' telt ook als hoog aeroob")
    elif focus.get("high") == "short":
        parts.append(f"tekort aan hoog aeroob ({fmt('high')}): de kwaliteitstraining is een drempeltraining")
    if focus.get("low") == "short":
        parts.append(f"tekort aan laag aeroob ({fmt('low')}): één kwaliteitstraining minder en meer rustige kilometers")
    text = ("Garmin-trainingsbalans (4 weken): " + "; ".join(parts) + ".") if parts else \
        "Garmin-trainingsbalans (4 weken) is in orde; het plan houdt de verdeling zo."
    return {"balance_focus": focus, "balance_text": text}


def habitual_days(runs, today, long_days):
    """Trainingsdagen afgeleid uit je laatste 8 weken (zolang je ze niet zelf hebt aangevinkt)."""
    recent = [r for r in runs if 0 < (today - dt.date.fromisoformat(r["date"])).days <= 56]
    count = [0] * 7
    for d in {r["date"] for r in recent}:
        count[dt.date.fromisoformat(d).weekday()] += 1
    n = min(6, max(3, round(len({r["date"] for r in recent}) / 8)))
    days = sorted(range(7), key=lambda d: (-count[d], d))[:n]
    if not any(d in long_days for d in days):
        best_long = max(long_days, key=lambda d: (count[d], d))
        days[-1] = best_long
    return sorted(days)


def AN_parse(s):
    """'45:00' / '1:45:00' -> seconden."""
    try:
        parts = [float(p) for p in str(s).split(":")]
    except ValueError:
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs if len(parts) > 1 else None


def planned_for(plan, date):
    """Geplande dag voor een datum (deze of volgende week)."""
    for w in (plan or {}).get("this_week", {}), (plan or {}).get("next_week", {}):
        for d in (w or {}).get("days", []):
            if d["date"] == date:
                return d
    return None
