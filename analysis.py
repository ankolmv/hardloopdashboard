"""Analyse per training, focuspunten voor techniek en een trainingssuggestie voor vandaag.

Alles is regelgebaseerd en werkt met de hartslagzones van het model (5 zones) en de
Daniels-trainingstempo's uit je huidige VDOT.
"""
import datetime as dt
import re
import statistics

import metrics as M
import store

TYPE_LABELS = {"herstel": "Herstelloop", "rustig": "Rustige duurloop", "lang": "Lange duurloop",
               "drempel": "Drempeltraining", "interval": "Intervaltraining"}
HARD_TYPES = ("drempel", "interval")
DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]


def mmss(s):
    if s is None:
        return "–"
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


# --------------------------------------------------------------------------- classificatie
def classify(r):
    """Welk soort training was dit? Op basis van naam, intervallen, Training Effect en duur."""
    name = (r.get("name") or "").lower()
    te = (r.get("te_label") or "").upper()
    if any(k in name for k in ("sprint", "interval", "vo2", "fartlek", "heuvel", "400", "800")) \
            or te in ("VO2MAX", "ANAEROBIC_CAPACITY", "SPRINT") or (r.get("te_anaerobic") or 0) >= 2:
        return "interval"
    if any(k in name for k in ("drempel", "threshold", "tempo")) or te == "LACTATE_THRESHOLD":
        return "drempel"
    if (r.get("minutes") or 0) >= 65 or (r.get("km") or 0) >= 12:
        return "lang"
    if (r.get("minutes") or 0) <= 35 and (r.get("te_aerobic") or 3) < 2.5:
        return "herstel"
    return "rustig"


def is_hard(r):
    return classify(r) in HARD_TYPES or (r.get("te_aerobic") or 0) >= 4


def zone_pct(r):
    z = r.get("zones") or []
    tot = sum(z) or 0
    return [round(x / tot * 100) for x in z] if tot else None


# --------------------------------------------------------------------------- analyse van één training
def analyze_session(r, runs, daily_by, zones, paces):
    """zones: lijst {from,to,name} (model, 5 zones); paces: Daniels-tempo's in s/km."""
    kind = classify(r)
    d = dt.date.fromisoformat(r["date"])
    zp = zone_pct(r) or []
    easy_pct = sum(zp[:2]) if zp else None
    z3, z4, z5 = (zp[2], zp[3], zp[4]) if len(zp) >= 5 else (None, None, None)
    splits = M.splits_per_km(store.streams(r["id"]))
    full = [s for s in splits if s["time"]]
    pacing = None
    if len(full) >= 4:
        h = len(full) // 2
        a = statistics.mean(s["time"] for s in full[:h])
        b = statistics.mean(s["time"] for s in full[h:])
        hr_a = statistics.mean(s["hr"] for s in full[:h] if s["hr"]) if any(s["hr"] for s in full[:h]) else None
        hr_b = statistics.mean(s["hr"] for s in full[h:] if s["hr"]) if any(s["hr"] for s in full[h:]) else None
        pacing = {"first": round(a), "second": round(b), "diff_pct": round((b / a - 1) * 100, 1),
                  "hr_first": round(hr_a) if hr_a else None, "hr_second": round(hr_b) if hr_b else None}

    prev = [x for x in runs if x["date"] < r["date"]]
    prev_day = [x for x in prev if x["date"] == (d - dt.timedelta(days=1)).isoformat()]
    hard_before = next((x for x in reversed(prev) if is_hard(x)), None)
    day = daily_by.get(r["date"], {})
    # Readiness vóór de training: laatste meting van die dag vóór de starttijd (anders de vorige dag)
    t0 = (r.get("start") or "")[11:16]
    before = [x for x in day.get("readiness_list") or [] if t0 and x.get("t") and x["t"] <= t0 and x.get("score") is not None]
    if before:
        ready, ready_t = before[-1]["score"], before[-1]["t"]
    elif day.get("readiness_list"):  # alleen metingen ná de training: vorige dag als benadering
        prev = daily_by.get((d - dt.timedelta(days=1)).isoformat(), {})
        ready, ready_t = prev.get("readiness"), None
    else:
        ready, ready_t = day.get("readiness"), day.get("readiness_time")
    ctx = {"readiness": ready, "readiness_time": ready_t, "sleep_h": day.get("sleep_h"), "hrv_status": day.get("hrv_status"),
           "acwr": day.get("acwr"),
           "prev_day": ({"name": prev_day[-1]["name"], "type": TYPE_LABELS[classify(prev_day[-1])],
                         "hard": is_hard(prev_day[-1])} if prev_day else None),
           "days_since_hard": (d - dt.date.fromisoformat(hard_before["date"])).days if hard_before else None,
           "temp_c": r.get("temp_c"), "humidity": r.get("humidity")}

    z2 = zones[1] if len(zones) > 1 else None
    tips, good = [], []
    tip = lambda tone, text: (good if tone == "good" else tips).append({"tone": tone, "text": text})

    # --- uitvoering t.o.v. het doel van dit type training
    efficiency = None
    if kind in ("rustig", "lang", "herstel") and easy_pct is not None and z2:
        st = store.streams(r["id"])
        hr, tm = st.get("heartrate") or [], st.get("time") or []
        top = z2["to"]
        samples = [(tm[i], hr[i]) for i in range(1, min(len(hr), len(tm))) if hr[i] and tm[i] >= 120]
        finish = None
        if samples and samples[-1][0] - samples[0][0] > 15 * 60:
            # Snel einde? Laatste 8 min duidelijk boven Z2 terwijl de rest rustig was
            end_t = samples[-1][0] - 8 * 60
            body = [h for t, h in samples if t < end_t]
            tail = [h for t, h in samples if t >= end_t]
            if body and tail and statistics.mean(tail) > top + 5 and statistics.mean(body) <= top + 2:
                finish = {"mins": 8, "hr": round(statistics.mean(tail)), "max": max(tail)}
                samples = [(t, h) for t, h in samples if t < end_t]
        tol = round(sum(1 for _, h in samples if h <= top + 3) / len(samples) * 100) if samples else easy_pct
        border = round(sum(1 for _, h in samples if top < h <= top + 3) / len(samples) * 100) if samples else 0
        part = " (los van de versnellingen aan het eind)" if finish else ""
        if tol >= 80:
            tip("good", f"Netjes rustig{part}: {tol}% in Z2 of maximaal 3 slagen erboven"
                        + (f" ({border}% net boven {top} bpm: grensgebied, voor je lichaam vrijwel hetzelfde)" if border >= 10 else "")
                        + f". Precies waar een {TYPE_LABELS[kind].lower()} voor is.")
        elif tol >= 65:
            tip("neutral", f"Grotendeels rustig{part}: {tol}% in Z2 of net erboven. Probeer het iets vaker onder {top} bpm te houden; "
                           f"een paar seconden per km langzamer is genoeg.")
        # Versnellingen (bijv. 6× 20 s) aan het eind horen bij de training: geen fout
        strides = next((m for m in (re.match(r"(\d+)x (\d+)s", x or "") for x in (r.get("intervals") or []))
                        if m and int(m.group(1)) >= 3 and int(m.group(2)) <= 40), None)
        if finish and strides:
            tip("good", f"Afgesloten met versnellingen ({strides.group(1)}× {strides.group(2)} s), zoals gepland. Die korte pieken "
                        f"(tot {finish['max']} bpm) horen erbij en verbeteren je loopeconomie; ze tellen niet als 'te hard'.")
        elif finish:
            tip("neutral", f"In de laatste {finish['mins']} min versnelde je (gem. {finish['hr']} bpm, max {finish['max']}). Prima als bewuste "
                           f"afsluiting, maar dat deel telt als Z3–Z4. Wil je de run helemaal rustig houden, blijf dan tot het eind onder {top} bpm.")
        # Efficiëntie: tempo per hartslag t.o.v. je eigen rustige runs van de laatste 6 weken (stijgt als je fitter wordt)
        ref = [x["ef"] for x in runs if x.get("ef") and x["date"] < r["date"] and classify(x) in ("rustig", "lang", "herstel")
               and (d - dt.date.fromisoformat(x["date"])).days <= 42]
        if r.get("ef") and len(ref) >= 3:
            pct = round((r["ef"] / statistics.median(ref) - 1) * 100, 1)
            efficiency = {"pct": pct, "n": len(ref)}
            if pct >= 1:
                tip("good", f"Efficiënt: {pct:+.1f}% meer tempo per hartslag dan je rustige runs van de laatste 6 weken. Je aerobe basis groeit.")
            elif pct <= -3:
                why = (" Logisch: gisteren deed je een zware training." if ctx["prev_day"] and ctx["prev_day"]["hard"]
                       else " Vaak vermoeidheid, warmte of weinig slaap; één run zegt weinig.")
                tip("neutral", f"Iets minder efficiënt dan normaal ({pct:+.1f}% tempo per hartslag).{why}")
        if tol < 65:
            tip("warn", f"Te zwaar voor een {TYPE_LABELS[kind].lower()}: maar {easy_pct}% in Z1–Z2 en {z3 or 0}% in Z3"
                        f"{f', {z4 + z5}% in Z4–Z5' if (z4 or 0) + (z5 or 0) >= 5 else ''}. "
                        f"Beter: hartslag {z2['from']}–{z2['to']} bpm"
                        f"{f', tempo ~{mmss(paces['E_fast'])}–{mmss(paces['E_slow'])}/km' if paces else ''}. "
                        f"Je bouwt zo dezelfde aerobe basis op met veel minder vermoeidheid.")
    elif kind == "drempel" and zp:
        if (z4 or 0) + (z3 or 0) >= 40 and (z5 or 0) <= 15:
            tip("good", f"Goede drempelprikkel: {(z3 or 0) + (z4 or 0)}% in Z3–Z4 en niet te veel in Z5.")
        elif (z5 or 0) > 15:
            tip("warn", f"{z5}% in Z5: dat is harder dan drempel. Drempel is 'comfortabel hard', "
                        f"hartslag {zones[3]['from']}–{zones[3]['to']}"
                        f"{f', tempo ~{mmss(paces['T'])}/km' if paces else ''}.")
        else:
            tip("neutral", f"Weinig tijd op drempelintensiteit ({z4 or 0}% in Z4). Mik de blokken op "
                           f"{zones[3]['from']}–{zones[3]['to']} bpm.")
    elif kind == "interval" and zp:
        tip("neutral", f"Intervaltraining: {(z4 or 0) + (z5 or 0)}% in Z4–Z5. Hartslag loopt bij korte blokken achter; "
                       f"stuur de blokken op tempo (~{mmss(paces['I'])}/km) in plaats van op hartslag." if paces else
                       "Intervaltraining: stuur korte blokken op tempo, niet op hartslag.")

    if pacing and kind in ("rustig", "lang", "drempel"):
        if pacing["diff_pct"] >= 3:
            tip("warn" if pacing["diff_pct"] >= 5 else "neutral", f"Te snel gestart: de tweede helft was {pacing['diff_pct']}% langzamer "
                        f"({mmss(pacing['first'])} → {mmss(pacing['second'])}/km). Begin 10–15 s/km rustiger.")
        elif pacing["diff_pct"] <= -2 and kind != "drempel":
            if (pacing["hr_second"] or 0) > (z2["to"] if z2 else 999):
                tip("neutral", f"Tweede helft sneller ({mmss(pacing['first'])} → {mmss(pacing['second'])}/km), maar je hartslag "
                               f"liep op naar {pacing['hr_second']}. Op een rustige run liever constant blijven.")
            else:
                tip("good", f"Mooi opgebouwd: tweede helft sneller ({mmss(pacing['second'])}/km) bij een rustige hartslag.")

    if r.get("decoupling") is not None and (r.get("minutes") or 0) >= 45:
        if r["decoupling"] <= 5:
            tip("good", f"Ontkoppeling {r['decoupling']}%: je hartslag bleef stabiel t.o.v. je tempo. Sterk uithoudingsvermogen.")
        else:
            tip("warn" if r["decoupling"] > 8 else "neutral", f"Ontkoppeling {r['decoupling']}%: je hartslag liep flink op t.o.v. je tempo. Begin rustiger, "
                        f"en drink bij runs > 75 min onderweg.")

    # --- omstandigheden
    if ctx["prev_day"] and ctx["prev_day"]["hard"] and (kind in HARD_TYPES or (r.get("te_aerobic") or 0) >= 4):
        tip("warn", f"Twee zware dagen achter elkaar (gisteren: {ctx['prev_day']['type'].lower()}). Na een zware training "
                    f"herstelt je lichaam pas na 36–48 uur. Plan er een rustige dag tussen.")
    if ctx["readiness"] is not None and ctx["readiness"] < 40 and (kind not in ("herstel", "rustig") or easy_pct is not None and easy_pct < 70):
        tip("warn", f"Training Readiness was {ctx['readiness']}: je lichaam was nog niet hersteld. Op zo'n dag levert "
                    f"een korte rustige run of rust meer op dan een stevige training.")
    if ctx["sleep_h"] and ctx["sleep_h"] < 6.5:
        tip("neutral", f"Je sliep {ctx['sleep_h']:.1f} uur. Dat verhoogt je hartslag bij hetzelfde tempo.")
    if r.get("pc_last") is not None:
        if r["pc_last"] <= -5:
            tip("neutral", f"Garmin Performance Condition zakte naar {r['pc_last']:+.0f} (start {r['pc_first']:+.0f}): je hartslag "
                           f"lag hoger dan verwacht bij dit tempo. Dat drukt de VO2max-schatting; meestal vermoeidheid.")
        elif r["pc_first"] is not None and r["pc_first"] >= 3:
            tip("good", f"Performance Condition {r['pc_first']:+.0f} bij de start: je was goed hersteld.")
    if r.get("temp_c") is not None and r["temp_c"] >= 20:
        tip("neutral", f"Het was {r['temp_c']} °C: warmte verhoogt je hartslag met 5–10 slagen. Pas je tempo aan.")

    verdict = ("Goed uitgevoerd" if not any(t["tone"] == "warn" for t in tips)
               else "Kan beter" if len([t for t in tips if t["tone"] == "warn"]) == 1 else "Aandachtspunten")
    if verdict == "Goed uitgevoerd" and any("versnelde je" in t["text"] for t in tips):
        verdict = "Goed, let op het einde"
    return {"type": kind, "type_label": TYPE_LABELS[kind], "verdict": verdict,
            "verdict_cls": "green" if verdict.startswith("Goed") else "orange" if verdict == "Kan beter" else "red",
            "zones_pct": zp, "pacing": pacing, "context": ctx, "good": good, "tips": tips, "efficiency": efficiency,
            "splits": [{**s, "pace": mmss(s["time"])} for s in splits]}


# --------------------------------------------------------------------------- techniek
TECH = {
    "cadence": {"label": "Cadans", "unit": "spm", "higher": True, "edges": [185, 174, 163, 151], "step": 2,
                "cue": "Kortere, snellere passen en landen onder je heup in plaats van voor je lichaam.",
                "drill": "Zet een metronoom (of muziek) op {target} bpm en loop daar 3× 2 min op tijdens een rustige run. "
                         "Twee keer per week 6× 20 s versnellingen."},
    "gct": {"label": "Grondcontacttijd", "unit": "ms", "higher": False, "edges": [218, 249, 278, 309], "step": 5,
            "cue": "Licht en veerkrachtig landen: voet snel weer van de grond, alsof de grond heet is.",
            "drill": "2× per week: touwtjespringen 3× 1 min, pogo-sprongen 3× 20, kuitheffen 3× 15."},
    "vo": {"label": "Verticale oscillatie", "unit": "cm", "higher": False, "edges": [6.4, 8.2, 9.8, 11.6], "step": 0.3,
           "cue": "Duw jezelf naar voren, niet omhoog: lichte voorover-lean vanuit je enkels, blik vooruit.",
           "drill": "A-skips en B-skips 2× 20 m voor je run; 1× per week 6–8 heuvelsprints van 10 s."},
    "vr": {"label": "Verticale ratio", "unit": "%", "higher": False, "edges": [6.1, 7.5, 8.7, 10.1], "step": 0.2,
           "cue": "Minder stuiteren én een krachtigere afzet naar achteren, zodat je pas langer wordt zonder omhoog te springen.",
           "drill": "1× per week heuvelsprints (6–8× 10 s), 2× per week krachtwerk: squats, lunges, step-ups 3× 10."},
}
RATING_NAMES = ["Uitstekend", "Goed", "Gemiddeld", "Onder gemiddeld", "Laag"]


def _rate(key, v):
    t, e = TECH[key], TECH[key]["edges"]
    if t["higher"]:
        return 0 if v > e[0] else 1 if v >= e[1] else 2 if v >= e[2] else 3 if v >= e[3] else 4
    return 0 if v < e[0] else 1 if v < e[1] else 2 if v < e[2] else 3 if v < e[3] else 4


def _tech_value(r, key):
    v = {"cadence": r.get("cadence"), "gct": r.get("gct"), "vr": r.get("vert_ratio"),
         "vo": (r.get("vert_osc") / 10) if r.get("vert_osc") else None}[key]
    return round(v, 1) if v is not None else None


def technique_focus(runs, today):
    """Kies de 1–2 punten met de meeste winst en check of het lukte in de laatste run."""
    recent = [r for r in runs if (today - dt.date.fromisoformat(r["date"])).days <= 28]
    if not recent:
        return None
    last = recent[-1]
    base_pool = recent[:-1] or recent
    items = []
    for key, t in TECH.items():
        vals = [v for r in recent if (v := _tech_value(r, key)) is not None]
        if len(vals) < 2:
            continue
        med = statistics.median(vals)
        rate = _rate(key, med)
        # Doel: de grens van de volgende betere categorie
        target = t["edges"][max(0, rate - 1)] if rate >= 1 else None
        # Vergelijk de laatste run met runs in een vergelijkbaar tempo (±20 s/km): techniek hangt af van tempo
        lv = _tech_value(last, key)
        similar = [v for r in base_pool if r is not last and r.get("pace_s_km") and last.get("pace_s_km")
                   and abs(r["pace_s_km"] - last["pace_s_km"]) <= 20 and (v := _tech_value(r, key)) is not None]
        base = statistics.median(similar) if len(similar) >= 2 else med
        delta = round(lv - base, 1) if lv is not None else None
        better = None
        if delta is not None:
            better = delta >= t["step"] if t["higher"] else delta <= -t["step"]
            worse = delta <= -t["step"] if t["higher"] else delta >= t["step"]
            better = True if better else (False if worse else None)
        items.append({"key": key, "label": t["label"], "unit": t["unit"], "median": round(med, 1), "rating": rate,
                      "rating_name": RATING_NAMES[rate], "target": target, "last": lv,
                      "last_rating": RATING_NAMES[_rate(key, lv)] if lv is not None else None,
                      "baseline": round(base, 1), "baseline_similar": len(similar) >= 2, "delta": delta,
                      "result": better, "cue": t["cue"],
                      "drill": t["drill"].format(target=round(target) if target and key == "cadence" else "")})
    order = {"vr": 0, "cadence": 1, "gct": 2, "vo": 3}
    items.sort(key=lambda x: (-x["rating"], order[x["key"]]))
    focus = [x for x in items if x["rating"] >= 2][:2]
    return {"focus": focus, "all": items, "last_run": {"id": last["id"], "name": last["name"], "date": last["date"],
                                                        "pace": mmss(last.get("pace_s_km"))}}


# --------------------------------------------------------------------------- suggestie voor vandaag
def suggest(runs, daily_by, zones, paces, today, long_days=(4, 5, 6), plan=None):
    """Eén concrete training voor vandaag (of morgen als je vandaag al gelopen hebt).
    Met een trainingsplan volgt het voorstel het plan, bijgestuurd op je herstel."""
    ran_today = any(r["date"] == today.isoformat() for r in runs)
    day = today + dt.timedelta(days=1) if ran_today else today
    wd = day.weekday()
    info = daily_by.get(today.isoformat(), {})
    readiness, acwr, sleep = info.get("readiness"), info.get("acwr"), info.get("sleep_h")
    week_start = M.week_start(day)
    this_week = [r for r in runs if week_start.isoformat() <= r["date"] < day.isoformat()]
    long_done = any(classify(r) == "lang" for r in this_week)
    quality = [r for r in this_week if classify(r) in HARD_TYPES]
    last = runs[-1] if runs else None
    last_hard = next((r for r in reversed(runs) if is_hard(r)), None)
    days_since_hard = (day - dt.date.fromisoformat(last_hard["date"])).days if last_hard else 9
    hard_yesterday = days_since_hard <= 1
    recent_long = [r["minutes"] for r in runs if (day - dt.date.fromisoformat(r["date"])).days <= 28]
    longest = max(recent_long) if recent_long else 60
    z = {i: (zn["from"] or 100, zn["to"]) for i, zn in enumerate(zones)}
    when = "morgen" if ran_today else "vandaag"
    why = []

    def hr(i):
        return [z[i][0], z[i][1]]

    if readiness is not None:
        why.append(f"Training Readiness {readiness}/100" + (f", slaap {sleep:.1f} u" if sleep else "")
                   + (" (stand van vandaag)" if ran_today else ""))
    if last:
        why.append(f"Laatste run: {TYPE_LABELS[classify(last)].lower()} op {DAYS_NL[dt.date.fromisoformat(last['date']).weekday()]}"
                   + (" (zwaar)" if is_hard(last) else ""))

    planned = None
    if plan:
        import plan as PL
        planned = PL.planned_for(plan, day.isoformat())
    if planned:
        kind, title, steps = planned["kind"], planned["title"], [dict(s) for s in planned["steps"]]
        hard_plan = kind in PL.QUALITY or kind == "lang"
        week = next(w for w in (plan["this_week"], plan["next_week"]) if planned in w["days"])
        slot = PL.free_slot(week, planned)
        moved = ("" if kind not in PL.QUALITY else f" {planned['title']} schuift door naar {slot['weekday']}." if slot
                 else f" {planned['title']} vervalt deze week: er is geen dag meer over die niet naast een andere zware training ligt.")
        if planned.get("moved_from"):
            why.append(f"Volgens plan (verplaatst van {planned['moved_from']}): {title}.")
        elif kind != "rust":
            why.append(f"Volgens je trainingsplan: {title}.")
        if readiness is not None and readiness < 30 and kind != "rust":
            kind, title, steps = "rust", "Rustdag (herstel laag)", []
            why.append(f"Je herstel is laag: {when} rust of hooguit 20–30 min wandelen levert het meeste op." + moved)
        elif kind == "rust":
            title = "Rustdag volgens plan"
            why.append("Vandaag staat er geen training op je plan. Rust hoort bij de opbouw; wil je toch bewegen, "
                       "wandel dan of loop hooguit 20–30 min heel rustig in Z1–Z2.")
        elif hard_plan and ((readiness is not None and readiness < 45) or (acwr and acwr > 1.5)
                            or (hard_yesterday and kind in PL.QUALITY)):
            reason = ("je had gisteren een zware training" if hard_yesterday and kind in PL.QUALITY
                      else f"je herstel is matig (Readiness {readiness})" if readiness is not None and readiness < 45
                      else f"je belasting stijgt snel (ACWR {acwr:.2f})")
            kind, title = "herstel", "Rustige herstelrun 30 min (Z2)"
            why.append(f"Aangepast omdat {reason}: kort en rustig in Z2, onderste helft (±{z[1][0] + 5}–{z[1][0] + 17} bpm)." + moved)
            steps = [{"kind": "run", "secs": 1800, "hr": hr(1), "pace": [paces["E_fast"], paces["E_slow"]],
                      "label": "Rustig in Z2 (onderste helft)"}]
        elif kind == "rustig" and readiness is not None and readiness < 45:
            kind, title = "herstel", "Rustige herstelrun 30 min (Z2)"
            why.append(f"Je herstel is matig (Readiness {readiness}): de rustige run wordt korter en extra rustig.")
            steps = [{"kind": "run", "secs": 1800, "hr": hr(1), "pace": [paces["E_fast"], paces["E_slow"]],
                      "label": "Rustig in Z2 (onderste helft)"}]
        else:
            if kind in PL.QUALITY and readiness is not None and readiness < 65:
                for s in steps:
                    if s["kind"] == "repeat" and s["n"] > 2:
                        s["n"] -= 1
                        title += " (1 herhaling minder)"
                        why.append("Readiness is matig, dus één herhaling minder dan gepland.")
                        break
            why += [w for w in planned.get("why", []) if w]

        def total(st):
            return sum(s["secs"] if s["kind"] != "repeat" else s["n"] * total(s["steps"]) for s in st)

        secs = total(steps)
        return {"date": day.isoformat(), "for_today": not ran_today, "weekday": DAYS_NL[wd], "kind": kind, "title": title,
                "why": why, "steps": steps, "minutes": round(secs / 60), "planned": planned["title"],
                "est_km": round(PL._km(steps, paces), 1) if secs else 0}

    if readiness is not None and readiness < 30:
        kind, title = "rust", "Rustdag"
        why.append(f"Je herstel is laag: {when} rust of hooguit 20–30 min wandelen levert het meeste op. "
                   f"Ververs morgenochtend; met een nieuwe Readiness kan het advies veranderen." if ran_today else
                   f"Je herstel is laag: {when} rust of hooguit 20–30 min wandelen levert het meeste op.")
        steps = []
    elif (readiness is not None and readiness < 45) or hard_yesterday or (acwr and acwr > 1.5):
        kind, title = "herstel", "Rustige herstelrun 30 min (Z2)"
        why.append("Na een zware training of bij matig herstel: kort en rustig in Z2, blijf in de onderste helft "
                   f"(±{z[1][0] + 5}–{z[1][0] + 17} bpm) en zeker niet in Z3." if hard_yesterday else
                   f"Je herstel is matig: kort en rustig in Z2, bij voorkeur in de onderste helft (±{z[1][0] + 5}–{z[1][0] + 17} bpm).")
        steps = [{"kind": "run", "secs": 1800, "hr": hr(1), "pace": [paces["E_fast"], paces["E_slow"]],
                  "label": "Rustig in Z2 (onderste helft)"}]
    elif wd in long_days and not long_done and (wd != 4 or (readiness or 60) >= 60):
        mins = int(min(110, max(60, round(longest * 1.1 / 5) * 5)))
        kind, title = "lang", f"Lange duurloop {mins} min"
        why.append(f"Je lange run valt op vrijdag–zondag en is deze week nog niet gedaan. "
                   f"Max ~10% langer dan je langste run van de laatste 4 weken ({round(longest)} min).")
        steps = [{"kind": "warmup", "secs": 600, "hr": hr(1), "label": "Inlopen"},
                 {"kind": "run", "secs": (mins - 10) * 60, "hr": hr(1), "pace": [paces["E_fast"], paces["E_slow"]],
                  "label": "Rustig in Z2"}]
    elif len(quality) < 2 and days_since_hard >= 2 and (readiness is None or readiness >= 50) and wd not in (5, 6):
        last_q = next((classify(r) for r in reversed(runs) if classify(r) in HARD_TYPES), "interval")
        lighter = readiness is not None and readiness < 65
        if last_q == "interval":
            reps, mins = (2, 12) if lighter else (3, 10)
            kind, title = "drempel", f"Drempeltraining {reps}× {mins} min"
            why.append("Je laatste kwaliteitstraining was een interval; nu drempel: het meest effectief voor 10 km tot halve marathon.")
            steps = [{"kind": "warmup", "secs": 900, "hr": hr(1), "label": "Inlopen"},
                     {"kind": "repeat", "n": reps, "steps": [
                         {"kind": "interval", "secs": mins * 60, "pace": [paces["T"] - 5, paces["T"] + 5], "hr": hr(3),
                          "label": "Drempeltempo"},
                         {"kind": "recovery", "secs": 120, "label": "Dribbelen"}]},
                     {"kind": "cooldown", "secs": 600, "label": "Uitlopen"}]
        else:
            reps = 4 if lighter else 5
            kind, title = "interval", f"Intervaltraining {reps}× 3 min"
            why.append("Je laatste kwaliteitstraining was drempel; nu VO2max-intervallen voor je snelheid.")
            steps = [{"kind": "warmup", "secs": 900, "hr": hr(1), "label": "Inlopen"},
                     {"kind": "repeat", "n": reps, "steps": [
                         {"kind": "interval", "secs": 180, "pace": [paces["I"] - 5, paces["I"] + 5], "label": "Interval"},
                         {"kind": "recovery", "secs": 150, "label": "Dribbelen"}]},
                     {"kind": "cooldown", "secs": 600, "label": "Uitlopen"}]
        if lighter:
            why.append("Readiness is matig, dus iets minder herhalingen dan normaal.")
    else:
        kind, title = "rustig", "Rustige duurloop 45 min + versnellingen"
        reason = ("Deze week staan er al twee kwaliteitstrainingen" if len(quality) >= 2
                  else "Je laatste zware training is pas net achter de rug" if days_since_hard < 2
                  else "Bewaar je energie voor de lange run in het weekend" if wd in (5, 6) or (wd == 4 and not long_done)
                  else "Een rustige dag houdt de opbouw in balans")
        why.append(reason + ": een rustige run in Z2 met korte versnellingen voor je loopeconomie.")
        steps = [{"kind": "run", "secs": 2400, "hr": hr(1), "pace": [paces["E_fast"], paces["E_slow"]], "label": "Rustig in Z2"},
                 {"kind": "repeat", "n": 6, "steps": [{"kind": "interval", "secs": 20, "label": "Versnelling (snel, ontspannen)"},
                                                      {"kind": "recovery", "secs": 60, "label": "Wandelen/dribbelen"}]},
                 {"kind": "cooldown", "secs": 300, "label": "Uitlopen"}]

    def total(st):
        return sum(s["secs"] if s["kind"] != "repeat" else s["n"] * total(s["steps"]) for s in st)

    secs = total(steps)
    return {"date": day.isoformat(), "for_today": not ran_today, "weekday": DAYS_NL[wd], "kind": kind, "title": title,
            "why": why, "steps": steps, "minutes": round(secs / 60),
            "est_km": round(secs / (paces["E_slow"] if kind in ("rustig", "lang", "herstel") else paces["T"] + 30), 1) if secs else 0}


# --------------------------------------------------------------------------- naar Garmin
def to_garmin_workout(sug, name_prefix="Dashboard"):
    from garminconnect.workout import (CustomHeartRateTarget, PaceTarget, RunningWorkout, WorkoutSegment,
                                       create_cooldown_step, create_recovery_step, create_repeat_group,
                                       create_targeted_interval_step, create_warmup_step)
    order = [0]

    def nxt():
        order[0] += 1
        return order[0]

    def build(s):
        if s["kind"] == "repeat":
            o = nxt()
            return create_repeat_group(s["n"], [build(c) for c in s["steps"]], o)
        o = nxt()
        if s["kind"] == "warmup":
            return create_warmup_step(s["secs"], o)
        if s["kind"] == "cooldown":
            return create_cooldown_step(s["secs"], o)
        if s["kind"] == "recovery":
            return create_recovery_step(s["secs"], o)
        target = None
        if s.get("pace"):  # tempo-doel (snel = hogere snelheid = bovengrens)
            target = PaceTarget(lower_limit=round(1000 / max(s["pace"]), 3), upper_limit=round(1000 / min(s["pace"]), 3))
        elif s.get("hr"):
            target = CustomHeartRateTarget(lower_limit=min(s["hr"]), upper_limit=max(s["hr"]))
        if s["kind"] == "run" and s.get("hr"):  # duurlopen sturen op hartslag
            target = CustomHeartRateTarget(lower_limit=min(s["hr"]), upper_limit=max(s["hr"]))
        return create_targeted_interval_step(s["secs"], o, target=target)

    steps = [build(s) for s in sug["steps"]]
    total = sum(s["secs"] if s["kind"] != "repeat" else s["n"] * sum(c["secs"] for c in s["steps"]) for s in sug["steps"])
    return RunningWorkout(
        workoutName=f"{name_prefix}: {sug['title']}"[:80], estimatedDurationInSecs=int(total),
        description=" ".join(sug["why"])[:500],
        workoutSegments=[WorkoutSegment(segmentOrder=1, sportType={"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
                                        workoutSteps=steps)])
