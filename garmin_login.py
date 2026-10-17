"""Eenmalig inloggen bij Garmin Connect.

Draai dit zelf in een terminal:  python garmin_login.py
Je e-mail en wachtwoord worden alleen gebruikt om tokens op te halen; het wachtwoord wordt niet
opgeslagen. De tokens komen in de map .garmin_tokens/ en blijven ongeveer een jaar geldig.
"""
import getpass
import os
import sys

from garminconnect import Garmin

import paths

TOKENS = paths.TOKENS


def main():
    print("Inloggen bij Garmin Connect (eenmalig)" + (f" - profiel '{paths.PROFILE}'" if paths.PROFILE else "") + "\n")
    email = input("E-mailadres Garmin: ").strip()
    password = getpass.getpass("Wachtwoord (wordt niet getoond of opgeslagen): ")
    os.makedirs(TOKENS, exist_ok=True)
    g = Garmin(email, password, prompt_mfa=lambda: input("Code uit e-mail/sms (MFA): ").strip())
    try:
        g.login(TOKENS)
    except Exception as e:  # noqa: BLE001
        print(f"\nInloggen mislukt: {e}")
        sys.exit(1)
    print(f"\nGelukt! Ingelogd als {g.get_full_name()}. Tokens opgeslagen in .garmin_tokens\\")
    print("Je kunt dit venster sluiten.")


if __name__ == "__main__":
    main()
