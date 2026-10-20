# Prestatiedashboard – hardlopen

Meet je loopprestaties met data uit intervals.icu en Garmin Connect, laat trends per weeknummer zien
en voorspelt welke tijd je haalt op je doelafstand als je je huidige trend doorzet.

## Setup
1. `pip install -r requirements.txt`
2. `.env` met `INTERVALS_ATHLETE_ID` en `INTERVALS_API_KEY` (zie `.env.example`).
3. Eenmalig Garmin koppelen: `python garmin_login.py` (tokens komen in `.garmin_tokens/`, ~1 jaar geldig).
4. Dubbelklik `start_dashboard.bat` → http://localhost:8765 en klik *Synchroniseren*.

## Tabs
| Tab | Inhoud |
|---|---|
| Overzicht | Doel, training voor vandaag (→ Garmin), analyse laatste training, kerncijfers, top-inzichten, techniek-focus |
| Prestaties | VDOT-trend + projectie, Garmin VO2max, voorspelde tijden (model vs Garmin), beste stukken, lactaatdrempel, Endurance/Hill Score |
| Training | Omvang, CTL/ATL/TSB, zones (HR/tempo), Training Effect, RPE vs belasting, scenario-schuif |
| Herstel | Training Readiness, HRV met baseline, slaap(fasen), Body Battery, stress, rusthartslag, HR-herstel |
| Techniek | Cadans, paslengte, verticale oscillatie/ratio, grondcontact, vermogen en efficiëntie, tempo bij vaste HR |
| Activiteiten | Alle runs; klik voor verloop, splits per km, beste stukken |

## Bestanden
| Bestand | Rol |
|---|---|
| `intervals_client.py` / `garmin_client.py` | API-koppelingen |
| `store.py` | Lokale cache in `data/` |
| `metrics.py` | VDOT, beste stukken, splits, efficiëntie, week- en dagreeksen |
| `projection.py` | Trend, projectie, doel, scenario |
| `analysis.py` | Analyse per training, techniek-focus, trainingssuggestie + Garmin-workout |
| `insights.py` | Inzichten in gewone taal |
| `app.py` (`build_payload`) + `static/index.html` | Server en dashboard |
| `goal.json` | Je doel: `{"distance_km": 10, "time": "42:00"}` |

## Hoe de cijfers tot stand komen
- **VDOT (Daniels & Gilbert)** uit (bijna) maximale stukken en uit rustige runs via hartslagreserve, gekalibreerd op je echte inspanningen.
- **Projectie**: gewogen trend van je week-VDOT (26 weken), max ~1 VDOT/maand, afvlakkend, met onzekerheidsband.
- **Duurcorrectie**: vanaf 10 km geleidelijk extra tijd bij weinig km/week of korte lange duurlopen.
- **Garmin Connect** gaat via de onofficiële `garminconnect`-library; als Garmin iets wijzigt valt alleen dat deel weg.

## Looproutes
Op Overzicht maakt het dashboard een route vanaf je startpunt: een rondje of heen-en-terug, met de eerste helft
tegen de wind in (wind via Open-Meteo, route via OpenRouteService). Eenmalig: maak een gratis sleutel op
openrouteservice.org en voer `set_ors_key.ps1` uit (zet hem in `.env` en als secret `ORS_KEY`).
Rondjes worden zelf opgebouwd (cirkel met de wind, tussenpunten naar populaire plekken), zonder heen-en-terug-stukken
(max 4% dubbel), eindigen eventueel tot 200 m voor de start, en hebben voorkeur voor groen/rustig, je eigen
looproutes (GPS) en populaire Strava-segmenten (optioneel: `python strava_login.py` + `set_strava_secrets.ps1`).

## Garmin-login: pc en cloud apart
De cloud ververst zijn Garmin-token bij elke run; daardoor wordt een gedeelde kopie ongeldig. Gebruik daarom op de
pc een eigen login (`python garmin_login.py`) en deel het tokenbestand niet met de cloud (die heeft zijn eigen token
in de versleutelde cache).

## Online via GitHub (alle apparaten)
De workflow `.github/workflows/dashboard.yml` draait elk uur (en bij acties vanaf de site):
cache terugzetten → actie → sync (intervals.icu + Garmin) → statische site bouwen → cache opslaan → GitHub Pages.

- Data op de site is versleuteld (AES-256-GCM, sleutel uit je wachtwoord). De cache staat versleuteld in de branch `state`.
- Secrets (Settings → Secrets → Actions): `INTERVALS_ATHLETE_ID`, `INTERVALS_API_KEY`, `GARMIN_TOKENS`
  (inhoud van `.garmin_tokens/garmin_tokens.json`), `DASHBOARD_PASSWORD`, `STATE_KEY` (willekeurige lange tekst).
- Knoppen op de site (sync, doel, Garmin-push, zones) starten de workflow met een fine-grained GitHub-token
  (alleen deze repository, permissie *Actions: Read and write*) dat je per apparaat invult via het tandwiel.
