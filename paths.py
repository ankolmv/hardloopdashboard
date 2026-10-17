"""Bestandslocaties per profiel.

Standaardprofiel = de projectmap zelf (.env, .garmin_tokens/, data/, goal.json).
Een ander profiel (HS_PROFILE=<naam>, of --profile <naam> op de commandline) krijgt een eigen
map profiles/<naam>/ met dezelfde indeling, zodat data van verschillende personen nooit mengt.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _profile():
    if "--profile" in sys.argv:
        i = sys.argv.index("--profile")
        if i + 1 < len(sys.argv):
            os.environ["HS_PROFILE"] = sys.argv[i + 1]
    return os.environ.get("HS_PROFILE") or ""


PROFILE = _profile()
BASE = os.path.join(HERE, "profiles", PROFILE) if PROFILE else HERE
os.makedirs(BASE, exist_ok=True)

ENV = os.path.join(BASE, ".env")
TOKENS = os.path.join(BASE, ".garmin_tokens")
DATA = os.path.join(BASE, "data")
GOAL = os.path.join(BASE, "goal.json")
