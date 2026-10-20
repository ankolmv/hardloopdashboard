"""Eenmalig Strava koppelen (officiële API, alleen-lezen). Zelf uitvoeren:  python strava_login.py

Vooraf: maak op https://www.strava.com/settings/api een app aan:
  - Application Name: bijv. "Hardloopdashboard"
  - Category: Training,  Website: http://localhost
  - Authorization Callback Domain: localhost
Daarna vind je daar je Client ID en Client Secret.
"""
import getpass
import http.server
import threading
import urllib.parse
import webbrowser

import strava_client

PORT = 8799


def main():
    print("Strava koppelen (eenmalig)\n")
    client_id = input("Client ID: ").strip()
    client_secret = getpass.getpass("Client Secret (wordt niet getoond): ").strip()
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update(code=(q.get("code") or [None])[0], error=(q.get("error") or [None])[0])
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Gelukt! Je kunt dit tabblad sluiten." if got.get("code") else "Geen toestemming gegeven."
            self.wfile.write(f"<h2 style='font-family:sans-serif'>{msg}</h2>".encode())
            threading.Thread(target=srv.shutdown, daemon=True).start()

    srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    url = "https://www.strava.com/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": f"http://localhost:{PORT}/exchange",
        "approval_prompt": "auto", "scope": "read"})
    print("\nJe browser opent nu de Strava-toestemmingspagina. Klik daar op 'Toestaan'.")
    print(f"(Opent er niets? Ga dan naar: {url})\n")
    webbrowser.open(url)
    srv.serve_forever()
    if not got.get("code"):
        print(f"Niet gekoppeld: {got.get('error') or 'geen code ontvangen'}")
        return
    strava_client.exchange_code(client_id, client_secret, got["code"])
    print("Gelukt! Tokens opgeslagen in .strava_tokens\\. Je kunt dit venster sluiten.")


if __name__ == "__main__":
    main()
