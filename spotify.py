"""Spotify als catalogus, in plaats van Apple Music.

Afspelen werkt sowieso: de Sonos-koppeling accepteert Spotify-links net zo goed,
zolang Spotify in de Sonos-app als muziekdienst is toegevoegd. Wat Spotify apart
nodig heeft is het zoeken, en daarvoor wil hun API een sleutelpaar.

Aanmaken op developer.spotify.com/dashboard: maak een app, kopieer de Client ID
en het Client Secret, en zet ze in spotify.json naast dit bestand:

    { "client_id": "...", "client_secret": "..." }

Of als omgevingsvariabelen SPOTIFY_CLIENT_ID en SPOTIFY_CLIENT_SECRET. Het is
gratis en je hoeft niets te publiceren; deze sleutels geven alleen toegang tot
de openbare catalogus, niet tot je eigen account of afspeellijsten.
"""

import base64
import json
import os
import time
from pathlib import Path

import requests

HERE = Path(__file__).parent
SLEUTELS = HERE / "spotify.json"

_token = {"waarde": None, "verloopt": 0}
_artiest_genres = {}


class GeenSleutels(RuntimeError):
    """Zonder client id en secret kan er niet gezocht worden."""


def sleutels():
    id_ = os.environ.get("SPOTIFY_CLIENT_ID")
    geheim = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not (id_ and geheim) and SLEUTELS.exists():
        data = json.loads(SLEUTELS.read_text(encoding="utf-8"))
        id_ = id_ or data.get("client_id")
        geheim = geheim or data.get("client_secret")
    if not (id_ and geheim):
        raise GeenSleutels(
            "Geen Spotify-sleutels gevonden. Maak een app op "
            "developer.spotify.com/dashboard en zet client_id en client_secret "
            f"in {SLEUTELS.name}."
        )
    return id_, geheim


def _koptekst():
    """Een token dat een uur meegaat, hergebruikt tot het verloopt."""
    if _token["waarde"] and time.time() < _token["verloopt"] - 30:
        return {"Authorization": f"Bearer {_token['waarde']}"}

    id_, geheim = sleutels()
    basis = base64.b64encode(f"{id_}:{geheim}".encode()).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basis}"},
        timeout=20,
    )
    if r.status_code == 400:
        raise GeenSleutels("Spotify wijst de sleutels af, kloppen ze wel?")
    r.raise_for_status()
    uit = r.json()
    _token["waarde"] = uit["access_token"]
    _token["verloopt"] = time.time() + uit.get("expires_in", 3600)
    return {"Authorization": f"Bearer {_token['waarde']}"}


def _haal(pad, params, tries=4):
    for poging in range(tries):
        r = requests.get(
            f"https://api.spotify.com/v1{pad}",
            params=params, headers=_koptekst(), timeout=20,
        )
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 2)) + poging)
            continue
        if r.status_code == 401:
            _token["verloopt"] = 0          # token verlopen, opnieuw halen
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Spotify blijft afwijzen, probeer het zo nog eens")


def genres_van(artiest_id):
    """Spotify hangt genres aan de artiest, niet aan het nummer."""
    if artiest_id in _artiest_genres:
        return _artiest_genres[artiest_id]
    try:
        data = _haal(f"/artists/{artiest_id}", {})
        genres = data.get("genres", [])
    except Exception:
        genres = []
    _artiest_genres[artiest_id] = genres
    return genres


def _naar_track(item, met_genre=True):
    artiesten = [a["name"] for a in item.get("artists", [])]
    plaatjes = item.get("album", {}).get("images", [])
    eerste = item.get("artists", [{}])[0].get("id")
    return {
        "url": item["external_urls"]["spotify"],
        "label": f"{', '.join(artiesten)} - {item['name']}",
        "art": plaatjes[0]["url"] if plaatjes else "",
        "genre": ", ".join(genres_van(eerste)[:3]) if (met_genre and eerste) else "",
        "preview": item.get("preview_url") or "",
        "artiest": artiesten[0] if artiesten else "",
        "duur": round((item.get("duration_ms") or 0) / 1000),
    }


def zoek(query, land="NL", limit=15, met_genre=True):
    data = _haal("/search", {
        "q": query, "type": "track", "limit": limit, "market": land,
    })
    return [_naar_track(x, met_genre) for x in data.get("tracks", {}).get("items", [])]


def van_artiest(naam, land="NL", limit=14):
    """Alles van deze artiest, om nieuwe nummers mee voor te stellen."""
    treffers = zoek(f'artist:"{naam}"', land, limit=limit, met_genre=False)
    plat = naam.lower()
    uit = [t for t in treffers if plat in t["label"].lower()]
    for t in uit:
        t["genre"] = ""      # genre pas ophalen als een nummer echt gekozen wordt
    return uit


def werkt():
    """Snelle controle voor de Setup-tab."""
    try:
        zoek("test", limit=1, met_genre=False)
        return True, "Spotify-sleutels werken"
    except GeenSleutels as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Spotify antwoordt niet: {exc}"
