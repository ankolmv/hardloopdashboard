"""Metrics die alleen in Garmin Connect zitten (via de onofficiële garminconnect-library).

Gebruikt de tokens uit .garmin_tokens/ (aanmaken met: python garmin_login.py).
Elk onderdeel is los afgeschermd: als Garmin iets niet levert of verandert, valt alleen dat weg.
"""
import datetime as dt
import logging
import os

HERE = os.path.dirname(os.path.abspath(__file__))
import paths
TOKENS = paths.TOKENS
log = logging.getLogger("garmin")


def available():
    return os.path.isdir(TOKENS) and any(os.scandir(TOKENS))


def connect():
    from garminconnect import Garmin
    g = Garmin()
    g.login(TOKENS)
    # Eventueel ververste tokens bewaren (belangrijk in de cloud, waar de cache tussen runs wordt opgeslagen)
    try:
        g.client.dump(TOKENS)
    except Exception as e:  # noqa: BLE001
        log.warning("Tokens bewaren mislukt: %s", e)
    return g


def _try(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("Garmin %s mislukt: %s", getattr(fn, "__name__", fn), e)
        return None


def _first(x):
    return x[0] if isinstance(x, list) and x else x


def _g(d, *path, default=None):
    for p in path:
        if isinstance(d, list):
            d = d[0] if d else None
        if not isinstance(d, dict):
            return default
        d = d.get(p)
    return default if d is None else d


# --------------------------------------------------------------------------- per dag
def fetch_day(g, day):
    """Compacte samenvatting van één dag."""
    ds = day.isoformat()
    out = {"date": ds}

    trs = _try(g.get_training_readiness, ds)
    trs = [x for x in (trs if isinstance(trs, list) else [trs]) if isinstance(x, dict) and x.get("score") is not None]
    # Garmin werkt readiness gedurende de dag bij: neem de meest recente meting, niet de eerste
    stamp = lambda x: str(x.get("timestampLocal") or x.get("timestamp") or "")
    tr = max(trs, key=stamp) if trs else None
    if isinstance(tr, dict):
        out["readiness_time"] = stamp(tr)[11:16] or None
        # Alle metingen van de dag (lokale tijd), zodat een analyse de waarde vóór een training kan gebruiken
        out["readiness_list"] = [{"t": stamp(x)[11:16], "score": x.get("score"), "level": x.get("level")}
                                 for x in sorted(trs, key=stamp) if stamp(x)[:10] == ds]
        morning = min(trs, key=stamp)
        if morning is not tr:
            out["readiness_morning"] = morning.get("score")
        out["readiness"] = tr.get("score")
        out["readiness_level"] = tr.get("level")
        out["readiness_feedback"] = tr.get("feedbackShort") or tr.get("feedbackLong")
        out["recovery_time_h"] = round(tr["recoveryTime"] / 60, 1) if tr.get("recoveryTime") else None
        out["acute_load"] = tr.get("acuteLoad")

    bb = _first(_try(g.get_body_battery, ds))
    if isinstance(bb, dict):
        vals = [v[1] for v in (bb.get("bodyBatteryValuesArray") or []) if isinstance(v, list) and len(v) > 1 and v[1] is not None]
        out["bb_charged"] = bb.get("charged")
        out["bb_drained"] = bb.get("drained")
        out["bb_high"] = max(vals) if vals else None
        out["bb_low"] = min(vals) if vals else None
        # Meest recente meting (niet de hoogste van de dag)
        pts = [v for v in (bb.get("bodyBatteryValuesArray") or []) if isinstance(v, list) and len(v) > 1 and v[1] is not None]
        if pts:
            last = max(pts, key=lambda v: v[0])
            out["bb_now"] = last[1]
            out["bb_now_time"] = dt.datetime.fromtimestamp(last[0] / 1000).strftime("%H:%M")

    us = _try(g.get_user_summary, ds)
    if isinstance(us, dict):
        out["stress_avg"] = us.get("averageStressLevel")
        out["stress_rest_s"] = us.get("restStressDuration")
        out["stress_high_s"] = us.get("highStressDuration")
        out["bb_wake"] = us.get("bodyBatteryAtWakeTime")
        if us.get("bodyBatteryMostRecentValue") is not None:
            out["bb_now"] = us["bodyBatteryMostRecentValue"]
        out["steps"] = us.get("totalSteps")
        out["intensity_min"] = (us.get("moderateIntensityMinutes") or 0) + 2 * (us.get("vigorousIntensityMinutes") or 0)
        out["resting_hr"] = us.get("restingHeartRate")

    ts = _try(g.get_training_status, ds)
    if isinstance(ts, dict):
        recent = _g(ts, "mostRecentTrainingStatus", "latestTrainingStatusData") or {}
        st = next(iter(recent.values()), {}) if isinstance(recent, dict) else {}
        out["training_status"] = st.get("trainingStatusFeedbackPhrase") or st.get("trainingStatus")
        lb = st.get("acuteTrainingLoadDTO") or {}
        out["acwr"] = lb.get("dailyAcuteChronicWorkloadRatio")
        out["load_acute"] = lb.get("dailyTrainingLoadAcute")
        out["load_chronic"] = lb.get("dailyTrainingLoadChronic")
        bal = _g(ts, "mostRecentTrainingLoadBalance", "metricsTrainingLoadBalanceDTOMap") or {}
        b = next(iter(bal.values()), {}) if isinstance(bal, dict) else {}
        out["load_aerobic_low"] = b.get("monthlyLoadAerobicLow")
        out["load_aerobic_high"] = b.get("monthlyLoadAerobicHigh")
        out["load_anaerobic"] = b.get("monthlyLoadAnaerobic")
        out["load_focus"] = b.get("trainingBalanceFeedbackPhrase")
        out["load_targets"] = {k: [b.get(f"monthlyLoad{g}TargetMin"), b.get(f"monthlyLoad{g}TargetMax")]
                               for k, g in (("low", "AerobicLow"), ("high", "AerobicHigh"), ("ana", "Anaerobic"))}
        vo2 = _g(ts, "mostRecentVO2Max", "generic")
        if isinstance(vo2, dict):
            out["vo2max"] = vo2.get("vo2MaxPreciseValue") or vo2.get("vo2MaxValue")

    hrv = _try(g.get_hrv_data, ds)
    if isinstance(hrv, dict):
        s = hrv.get("hrvSummary") or {}
        out["hrv_night"] = s.get("lastNightAvg")
        out["hrv_week"] = s.get("weeklyAvg")
        out["hrv_status"] = s.get("status")
        bl = s.get("baseline") or {}
        out["hrv_base_lo"] = bl.get("balancedLow")
        out["hrv_base_hi"] = bl.get("balancedUpper")

    sl = _try(g.get_sleep_data, ds)
    if isinstance(sl, dict):
        dto = sl.get("dailySleepDTO") or {}
        out["sleep_s"] = dto.get("sleepTimeSeconds")
        out["sleep_deep_s"] = dto.get("deepSleepSeconds")
        out["sleep_rem_s"] = dto.get("remSleepSeconds")
        out["sleep_light_s"] = dto.get("lightSleepSeconds")
        out["sleep_awake_s"] = dto.get("awakeSleepSeconds")
        out["sleep_score"] = _g(dto, "sleepScores", "overall", "value")
        out["respiration"] = dto.get("averageRespirationValue")
    return {k: v for k, v in out.items() if v is not None}


# --------------------------------------------------------------------------- momentopnames
def fetch_snapshot(g, today):
    out = {"date": today.isoformat()}
    rp = _try(g.get_race_predictions)
    rp = _first(rp)
    if isinstance(rp, dict):
        out["race"] = {k: rp.get(f) for k, f in (("5k", "time5K"), ("10k", "time10K"), ("hm", "timeHalfMarathon"), ("m", "timeMarathon"))}

    hz = _try(g.get_heart_rate_zones_v2) or _try(g.get_heart_rate_zones)
    if isinstance(hz, list) and hz:
        z = next((x for x in hz if x.get("sport") == "RUNNING"), None) or next((x for x in hz if x.get("sport") == "DEFAULT"), hz[0])
        out["hr_zones_all"] = {x.get("sport"): [x.get(f"zone{i}Floor") for i in range(1, 6)] for x in hz}
        out["hr_zones"] = {"method": z.get("trainingMethod"), "max": z.get("maxHeartRateUsed"),
                           "rest": z.get("restingHeartRateUsed"), "lthr": z.get("lactateThresholdHeartRateUsed"),
                           "floors": [z.get(f"zone{i}Floor") for i in range(1, 6)], "sport": z.get("sport")}

    lt = _try(g.get_lactate_threshold)
    if isinstance(lt, dict):
        hr = _g(lt, "heart_rate") or _g(lt, "speed_and_heart_rate") or {}
        sp = _g(lt, "speed_and_heart_rate") or {}
        out["lt_hr"] = hr.get("heartRate") or sp.get("heartRate")
        spd = sp.get("speed")
        if spd:  # Garmin geeft m/s (soms /10)
            spd = spd * 10 if spd < 1 else spd
            out["lt_pace_s"] = round(1000 / spd)

    start = (today - dt.timedelta(days=180)).isoformat()
    lth = _try(g.get_lactate_threshold, latest=False, start_date=start, end_date=today.isoformat(), aggregation="weekly")
    if isinstance(lth, dict):
        hrs = {x.get("from"): x.get("value") for x in lth.get("heart_rate") or []}
        out["lt_hist"] = [{"date": x.get("updatedDate") or x.get("from"), "pace_s": round(1000 / (x["value"] * 10)),
                           "hr": hrs.get(x.get("from"))} for x in lth.get("speed") or [] if x.get("value")]
    es = _try(g.get_endurance_score, start, today.isoformat())
    if isinstance(es, dict):
        out["endurance"] = _g(es, "avg") or _g(es, "overallScore")
        out["endurance_class"] = _g(es, "enduranceScoreDTO", "classification")
        groups = es.get("groupMap") or {}
        out["endurance_hist"] = [{"week": k, "score": v.get("groupAverage")} for k, v in sorted(groups.items())
                                 if isinstance(v, dict) and v.get("groupAverage")]
    hs = _try(g.get_hill_score, start, today.isoformat())
    if isinstance(hs, dict):
        lst = hs.get("hillScoreDTOList") or []
        if lst:
            last = lst[-1]
            out["hill"] = last.get("overallScore")
            out["hill_strength"] = last.get("strengthScore")
            out["hill_endurance"] = last.get("enduranceScore")
        out["hill_hist"] = [{"date": x.get("calendarDate"), "score": x.get("overallScore")} for x in lst if x.get("overallScore")]
    return out


STREAM_KEYS = {"sumDuration": "time", "sumDistance": "distance", "directHeartRate": "heartrate",
               "directSpeed": "velocity_smooth", "directRunCadence": "cadence", "directPower": "watts",
               "directElevation": "altitude", "directLatitude": "lat", "directLongitude": "lng"}


def fetch_run(g, garmin_id, ctx):
    """Volledige run uit Garmin, omgezet naar dezelfde vorm als een intervals.icu-activiteit.

    Gebruikt voor runs die in intervals.icu alleen als (lege) Strava-kopie staan.
    ctx: {"rest_hr", "lthr", "hr_zones"} voor de belastingsschatting en hartslagzones.
    """
    a = g.get_activity(garmin_id)
    s = a.get("summaryDTO") or {}
    d = g.get_activity_details(garmin_id, maxchart=4000, maxpoly=0) or {}
    idx = {m["key"]: m["metricsIndex"] for m in d.get("metricDescriptors") or []}
    rows = [r.get("metrics") or [] for r in d.get("activityDetailMetrics") or []]
    streams = {}
    for gk, ik in STREAM_KEYS.items():
        if gk in idx:
            i = idx[gk]
            streams[ik] = [r[i] if i < len(r) else None for r in rows]
    if "time" in streams:
        t0 = next((t for t in streams["time"] if t is not None), 0)
        streams["time"] = [round((t or 0) - t0) for t in streams["time"]]

    mins = (s.get("movingDuration") or s.get("duration") or 0) / 60
    hr = s.get("averageHR")
    rest, lthr = ctx.get("rest_hr") or 50, ctx.get("lthr") or 170
    load = None
    if hr and lthr > rest:  # HR-gebaseerde schatting (vergelijkbaar met hrTSS)
        ratio = max(0.0, (hr - rest) / (lthr - rest))
        load = round(mins / 60 * ratio ** 2 * 100)
    zones = None
    hz, hs = ctx.get("hr_zones"), streams.get("heartrate")
    if hz and hs:
        zones = [0] * 7
        for h in hs:
            if h:
                zones[min(next((i for i, b in enumerate(hz) if h <= b), len(hz)), 6)] += 1
    rpe = s.get("directWorkoutRpe")
    act = {
        "id": f"g{garmin_id}", "source": "GARMIN_DIRECT", "type": "Run",
        "name": a.get("activityName"),
        "start_date_local": (s.get("startTimeLocal") or "")[:19].replace(" ", "T"),
        "distance": s.get("distance"), "moving_time": round(mins * 60), "elapsed_time": s.get("elapsedDuration"),
        "average_heartrate": round(hr) if hr else None, "max_heartrate": s.get("maxHR"),
        "average_speed": s.get("averageMovingSpeed") or s.get("averageSpeed"),
        "pace": s.get("averageMovingSpeed") or s.get("averageSpeed"), "gap": s.get("avgGradeAdjustedSpeed"),
        "average_cadence": (s.get("averageRunCadence") or 0) / 2 or None,
        "average_stride": (s.get("strideLength") or 0) / 100 or None,
        "average_vertical_oscillation": (s.get("verticalOscillation") or 0) * 10 or None,  # cm -> mm (zoals intervals)
        "average_vertical_ratio": s.get("verticalRatio"), "average_stance_time": s.get("groundContactTime"),
        "total_elevation_gain": s.get("elevationGain"), "calories": s.get("calories"),
        "icu_rpe": round(rpe / 10) if rpe else None, "icu_training_load": load, "icu_hr_zone_times": zones,
        "load_estimated": True,
    }
    return act, streams


def fetch_run_extra(g, garmin_id):
    """Performance Condition-verloop en weer van één run (voor de trainingsanalyse)."""
    out = {}
    d = _try(g.get_activity_details, garmin_id, maxchart=2000, maxpoly=0) or {}
    idx = {m["key"]: m["metricsIndex"] for m in d.get("metricDescriptors") or []}
    if "directPerformanceCondition" in idx:
        i = idx["directPerformanceCondition"]
        pc = [r["metrics"][i] for r in d.get("activityDetailMetrics") or [] if i < len(r.get("metrics") or []) and r["metrics"][i] is not None]
        if pc:
            out["pc_first"] = pc[0]
            out["pc_last"] = pc[-1]
            out["pc_min"] = min(pc)
            out["pc_max"] = max(pc)
    w = _try(g.get_activity_weather, garmin_id)
    if isinstance(w, dict) and w.get("temp") is not None:
        out["temp_c"] = round((w["temp"] - 32) * 5 / 9)  # Garmin geeft Fahrenheit
        out["humidity"] = w.get("relativeHumidity")
        out["wind_kmh"] = round(w["windSpeed"] * 1.609) if w.get("windSpeed") is not None else None
        out["weather"] = (w.get("weatherTypeDTO") or {}).get("desc")
    return out


def fetch_activities(g, start, end):
    acts = _try(g.get_activities_by_date, start.isoformat(), end.isoformat()) or []
    out = []
    for a in acts:
        out.append({
            "garmin_id": a.get("activityId"),
            "start": a.get("startTimeLocal"),
            "type": _g(a, "activityType", "typeKey"),
            "te_aerobic": a.get("aerobicTrainingEffect"),
            "te_anaerobic": a.get("anaerobicTrainingEffect"),
            "te_label": a.get("trainingEffectLabel"),
            "te_message": a.get("aerobicTrainingEffectMessage"),
            "garmin_load": a.get("activityTrainingLoad"),
            "max_hr": a.get("maxHR"),
            "vo2max": a.get("vO2MaxValue"),
            "body_battery_delta": a.get("differenceBodyBattery"),
            "stamina_end": a.get("endStamina") if a.get("endStamina") is not None else a.get("minAvailableStamina"),
        })
    return out
