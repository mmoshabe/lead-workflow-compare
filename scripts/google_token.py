"""Short-lived Google access token for the test harness, from the local n8n Google credential.

Reuses the booking assistant's local n8n credential (it has the spreadsheets scope), refreshes it, and
caches the access token (never the refresh token) for 50 minutes. Nothing is printed except status.

    python3 scripts/google_token.py <cache-file>
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

BOOKING = Path(__file__).resolve().parents[2] / "booking-assistant"


def env(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def token(cache: Path) -> str:
    if cache.exists() and time.time() - cache.stat().st_mtime < 50 * 60:
        return cache.read_text().strip()
    e = env(BOOKING / ".env")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "cred.json"
        subprocess.run([str(BOOKING / "scripts/n8n.sh"), "export:credentials", f"--id={e['N8N_GOOGLE_CRED_ID']}",
                        "--decrypted", f"--output={out}"], cwd=BOOKING, check=True,
                       env={**os.environ, "N8N_RUNNERS_BROKER_PORT": "5690"},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        refresh = json.loads(out.read_text())[0]["data"]["oauthTokenData"]["refresh_token"]
    body = urllib.parse.urlencode({"client_id": e["GOOGLE_CLIENT_ID"], "client_secret": e["GOOGLE_CLIENT_SECRET"],
                                   "refresh_token": refresh, "grant_type": "refresh_token"}).encode()
    access = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=20))["access_token"]
    cache.write_text(access)
    cache.chmod(0o600)
    return access


if __name__ == "__main__":
    token(Path(sys.argv[1]))
    print("token cached")
