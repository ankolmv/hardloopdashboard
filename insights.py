"""Automatische inzichten in gewone taal, per categorie."""
import statistics

import metrics as M


def _pace(s):
    if not s:
        return "–"
    m, s = divmod(int(round(s)), 60)
    return f"{m}:{s:02d}/km"


def _time(s):
    s = int(round(s))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _recent(daily, key, n):
    return [d[key] for d in daily[-n:] if d.get(key) is not None]


def build(weeks, runs, tr, hr_ref, pace_ref, n_weeks, daily, snap, model_preds, zone_labels=("Z1–Z2", "Z3", None)):
    """Lijst van {cat, tone, title, text}. tone: good | warn | neutral | info."""
    out = []
    add = lambda cat, tone, title, text: out.append({"cat": cat, "tone": tone, "title": title, "text": text})
    active = [w for w in weeks if w["runs"]]

    # ---- Prestatie
    if tr and tr["n"] >= 3:
        pm = tr["raw_slope"] * 4.35
        if abs(pm) < 0.2:
            add("prestatie", "neutral", "Stabiel niveau", f"Je VDOT schommelt rond {tr['now']:.1f}.")
        elif pm > 0:
            sec5k = M.race_time(tr["now"], 5000) - M.race_time(tr["now"] + pm, 5000)
            capped = " De projectie rekent voorzichtiger (max ~1 per maand)." if tr["raw_slope"] > tr["slope"] else ""
            add("prestatie", "good", "Je wordt sneller",
                f"Je VDOT stijgt ~{pm:.1f} per maand, ongeveer {sec5k:.0f} s winst op 5 km per maand.{capped}")
        else:
            add("prestatie", "warn", "Dalende lijn", f"Je VDOT daalt ~{abs(pm):.1f} per maand. Kijk naar herstel, slaap en omvang.")

    vo2 = next((d["vo2max"] for d in reversed(daily) if d.get("vo2max")), None)
    if vo2 and tr:
        gap = vo2 - tr["now"]
        if gap > 4:
            add("prestatie", "info", "Je motor is groter dan je resultaten",
                f"Garmin schat je VO2max op {vo2:.0f}, je wedstrijdniveau (VDOT) is {tr['now']:.1f}. Dat verschil "
                f"van {gap:.0f} punten zit in loopeconomie en uithoudingsvermogen: veel rustige kilometers, "
                f"langere duurlopen en drempeltraining zetten je motor beter om in snelheid.")

    gp = (snap or {}).get("race") or {}
    if gp.get("10k") and model_preds.get("10k"):
        diff = model_preds["10k"] - gp["10k"]
        add("prestatie", "neutral", "Garmin vs. model",
            f"Garmin voorspelt {_time(gp['10k'])} op 10 km, het model {_time(model_preds['10k'])}. "
            + ("Garmin is optimistischer: het baseert zich vooral op VO2max." if diff > 30 else
               "Ze liggen dicht bij elkaar." if abs(diff) <= 30 else "Het model is optimistischer dan Garmin."))

    pr = [p for p in pace_ref if p.get("pace")]
    if len(pr) >= 3:
        first = statistics.mean(p["pace"] for p in pr[:2])
        last = statistics.mean(p["pace"] for p in pr[-2:])
        d = first - last
        if abs(d) >= 3:
            add("prestatie", "good" if d > 0 else "warn", "Aerobe fitheid",
                f"Bij hartslag {hr_ref} loop je nu {_pace(last)}: {abs(d):.0f} s/km "
                f"{'sneller' if d > 0 else 'langzamer'} dan aan het begin van de periode.")

    # ---- Training
    if len(weeks) >= 4:
        a = sum(w["km"] for w in weeks[-2:])
        b = sum(w["km"] for w in weeks[-4:-2])
        if b > 10 and a > b * 1.3:
            add("training", "warn", "Snelle opbouw",
                f"Je omvang steeg {round((a / b - 1) * 100)}% in 2 weken ({b:.0f} → {a:.0f} km). "
                f"Sprongen van >30% gaan samen met meer blessures.")
    zl = [w for w in active[-4:] if w.get("z_low") is not None]
    if zl:
        low = statistics.mean(w["z_low"] for w in zl)
        mid = statistics.mean(w["z_mid"] for w in zl)
        if low < 70:
            easy, midl, cap = zone_labels
            add("training", "warn", "Te vaak 'gemiddeld hard'",
                f"{low:.0f}% van je looptijd was rustig ({easy}) en {mid:.0f}% in {midl}. Sterke duurlopers "
                f"doen ~80% rustig." + (f" Houd rustige runs onder {cap} bpm." if cap else " Rustiger rustige runs = meer progressie."))
        else:
            add("training", "good", "Goede intensiteitsverdeling", f"{low:.0f}% van je looptijd was rustig.")
    acwr = next((d["acwr"] for d in reversed(daily) if d.get("acwr")), None)
    if acwr:
        if acwr > 1.5:
            add("training", "warn", "Belasting piekt", f"Je acute/chronische belasting is {acwr:.1f} (Garmin). Boven 1,5 stijgt het blessurerisico.")
        elif acwr < 0.8:
            add("training", "neutral", "Rustige periode", f"Je acute/chronische belasting is {acwr:.1f}: je traint minder dan je gewend bent.")
    tea = [r["te_aerobic"] for r in runs[-10:] if r.get("te_aerobic")]
    if len(tea) >= 4:
        high = sum(1 for x in tea if x >= 4)
        if high >= len(tea) * 0.5:
            add("training", "warn", "Veel zware prikkels",
                f"{high} van je laatste {len(tea)} runs had een aerobe Training Effect ≥ 4. Wissel af met echt rustige runs (TE 2-3).")
    dec = [r["decoupling"] for r in runs[-8:] if r.get("decoupling") is not None]
    if dec and statistics.median(dec) > 5:
        add("training", "neutral", "Duurvermogen", f"Op langere runs loopt je hartslag ~{statistics.median(dec):.0f}% op t.o.v. je tempo. "
                                                  f"Onder 5% = sterke aerobe basis. Langere rustige duurlopen helpen.")

    # ---- Herstel
    hrv7, hrv28 = _recent(daily, "hrv", 7), _recent(daily, "hrv", 28)
    if len(hrv7) >= 4 and len(hrv28) >= 14:
        r = statistics.mean(hrv7) / statistics.mean(hrv28) - 1
        if r < -0.07:
            add("herstel", "warn", "HRV lager dan normaal", f"Je HRV is deze week {abs(r) * 100:.0f}% onder je maandgemiddelde. Plan wat rust in.")
        elif r > 0.05:
            add("herstel", "good", "Goed hersteld", f"Je HRV ligt {r * 100:.0f}% boven je maandgemiddelde.")
    sl = _recent(daily, "sleep_h", 7)
    if len(sl) >= 4:
        avg = statistics.mean(sl)
        add("herstel", "warn" if avg < 7 else "good", "Slaap",
            f"Gemiddeld {avg:.1f} uur per nacht deze week." + (" Onder 7 uur herstel je trager." if avg < 7 else ""))
    rd = _recent(daily, "readiness", 7)
    if rd:
        add("herstel", "good" if rd[-1] >= 60 else "warn" if rd[-1] < 40 else "neutral", "Training Readiness",
            f"Vandaag {rd[-1]:.0f}/100 (gemiddeld {statistics.mean(rd):.0f} deze week).")
    bb = _recent(daily, "bb_high", 7)
    if len(bb) >= 3 and statistics.mean(bb) < 60:
        add("herstel", "warn", "Body Battery laag", f"Je Body Battery komt gemiddeld maar tot {statistics.mean(bb):.0f}. Je laadt 's nachts onvoldoende op.")

    # ---- Techniek
    cad = [w["cadence"] for w in active if w.get("cadence")]
    if len(cad) >= 4 and abs(cad[-1] - cad[0]) >= 3:
        add("techniek", "neutral", "Cadans", f"Je cadans ging van {cad[0]:.0f} naar {cad[-1]:.0f} stappen/min.")
    eff = [w["eff_power"] for w in active if w.get("eff_power")]
    if len(eff) >= 4:
        d = (statistics.mean(eff[-2:]) / statistics.mean(eff[:2]) - 1) * 100
        if abs(d) >= 2:
            add("techniek", "good" if d > 0 else "warn", "Loopefficiëntie",
                f"Je haalt {abs(d):.0f}% {'meer' if d > 0 else 'minder'} snelheid uit elke watt dan aan het begin van de periode.")
    gp = [w["gct"] for w in active if w.get("gct")]
    if gp and statistics.mean(gp[-3:]) > 270:
        add("techniek", "neutral", "Grondcontact", f"Je grondcontacttijd is ~{statistics.mean(gp[-3:]):.0f} ms. Korte versnellingen en sprongkracht helpen dit omlaag te krijgen.")

    if n_weeks < 6:
        add("prestatie", "info", "Nog weinig data", f"Pas {n_weeks} weken met volledige data; trends worden elke week betrouwbaarder.")
    return out
