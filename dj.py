"""Sonos DJ - draait een setlist van Apple Music-tracks op je Sonos.

Gebruik:
    python dj.py speakers                 lijst je Sonos-speakers
    python dj.py check                    resolve de setlist, speelt niks af
    python dj.py live                     start de set en blijft draaien
    python dj.py ui                       webinterface: alles vanaf je telefoon
    python dj.py next                     skip naar het volgende nummer
    python dj.py vol 30                   zet volume (fade)
    python dj.py stop                     stop en leeg de queue

Tijdens 'live' mag setlist.json aangepast worden: nieuwe tracks worden
automatisch bijgequeued zonder dat de muziek stopt.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests
import soco
import soco.discovery
from soco.plugins.sharelink import ShareLinkPlugin

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
SETLIST = HERE / "setlist.json"
CACHE = HERE / ".track-cache.json"

# versies die je bijna nooit wilt als je een nummer zoekt voor een set
JUNK = re.compile(
    r"\b(karaoke|tribute|made popular by|in the style of|instrumental|acoustic"
    r"|radio edit|radio mix|sped up|slowed|live (at|from|version))\b|\(live\)",
    re.I,
)


STOPWORDS = {
    "de", "het", "een", "en", "van", "in", "op", "je", "me", "mijn", "dan", "nou",
    "the", "a", "an", "and", "of", "to", "for", "my", "you", "feat", "ft", "with",
}

# onder deze score is het resultaat een willekeurig nummer en geen match
MIN_SCORE = 2.0

_last_call = 0.0


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _norm(text):
    """Alles naar kleine letters en losse woorden, met spaties eromheen."""
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def _artist_names(artist_field):
    """Splits "Sonny Fodera, Jazzy & D.O.D" in losse artiestnamen."""
    parts = re.split(
        r",|&|\bx\b|\bvs\b|\band\b|\bfeat\b|\bft\b|\bwith\b",
        artist_field,
        flags=re.I,
    )
    return [n for n in (_norm(p).strip() for p in parts) if n]


def _core_title(title):
    """Titel zonder het (feat. ...)-staartje."""
    return re.sub(r"[\(\[]\s*(feat|ft|with)\.?.*?[\)\]]", "", title, flags=re.I)


def _search(query, country, tries=5):
    """iTunes-zoekopdracht, netjes getempo'd en met backoff op rate limits."""
    global _last_call
    for attempt in range(tries):
        wait = 0.35 - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        r = requests.get(
            "https://itunes.apple.com/search",
            params={
                "term": query,
                "media": "music",
                "entity": "song",
                "limit": 15,
                "country": country,
            },
            timeout=20,
        )
        _last_call = time.time()
        # iTunes knijpt af met 429, maar ook met 403 als je te snel gaat
        if r.status_code in (403, 429, 503):
            time.sleep(3 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json().get("results", [])
    raise RuntimeError(
        "iTunes houdt de boot af. Even wachten en het opnieuw proberen."
    )


def _score(item, query):
    """Hoe goed past dit zoekresultaat bij wat er gevraagd is."""
    q = _tokens(query)
    artist = _tokens(item.get("artistName", ""))
    title = _tokens(item.get("trackName", ""))

    score = 0.0
    if artist:
        score += 5.0 * len(artist & q) / len(artist)
    if title:
        score += 3.0 * len(title & q) / len(title)
        # extra tekst in de titel die niet gevraagd is (remix, versie, feat)
        score -= 0.4 * len(title - q)
    if JUNK.search(item.get("trackName", "") + " " + item.get("collectionName", "")):
        score -= 10.0
    return score


# ---------------------------------------------------------------- Apple Music

# hoog dit op als de matching verandert, dan vervalt de oude cache vanzelf
CACHE_VERSION = 7


def _cache():
    if CACHE.exists():
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        if data.get("_version") == CACHE_VERSION:
            return data
    return {"_version": CACHE_VERSION}


def _cache_write(data):
    CACHE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve(query, country="NL"):
    """Zoek 'artiest - titel' op en geef (apple_music_url, label) terug."""
    hit = resolve_info(query, country)
    return (hit["url"], hit["label"]) if hit else (None, None)


def resolve_info(query, country="NL"):
    """Als resolve, maar met albumhoes erbij. None als er niks past."""
    cache = _cache()
    key = f"{country}:{query.lower().strip()}"
    if key in cache:
        return cache[key]

    results = _search(query, country)
    if not results:
        return None

    # iTunes sorteert op populariteit; wij willen de versie die echt gevraagd is
    best = max(results, key=lambda x: _score(x, query))

    # iTunes geeft altijd iets terug, ook als het nergens op slaat. Zonder deze
    # drempel belandt "3robi Adem In" als Robin Thicke in de set.
    if _score(best, query) < MIN_SCORE:
        return None
    q = _tokens(query)
    # minstens een echt woord uit de titel moet gevraagd zijn; op alleen "the"
    # of "dan" matchen levert het verkeerde nummer van de juiste artiest op.
    # Het feat-gedeelte telt niet mee, anders matcht elk nummer waar de gezochte
    # artiest toevallig gastrapper op is.
    if not (_tokens(_core_title(best.get("trackName", ""))) & q) - STOPWORDS:
        return None
    # en een complete artiestnaam moet in de zoekopdracht staan. Op losse
    # woorden matchen maakt van "James Hype Ferrari" een track van Vlad James.
    nq = _norm(query)
    if not any(f" {a} " in nq for a in _artist_names(best.get("artistName", ""))):
        return None

    hit = {
        "url": best["trackViewUrl"],
        "label": f"{best['artistName']} - {best['trackName']}",
        "art": best.get("artworkUrl100", "").replace("100x100", "600x600"),
        "genre": best.get("primaryGenreName", ""),
        "duur": round((best.get("trackTimeMillis") or 0) / 1000),
    }
    cache[key] = hit
    _cache_write(cache)
    return hit


# iTunes-genres terug naar de twee hoeken die jij aangeeft
HIPHOP = ("hip-hop", "hiphop", "rap", "r&b", "urban", "nederhop", "soul")
HOUSE = ("dance", "house", "electronic", "elektronisch", "techno", "edm",
         "garage", "breakbeat", "club")


def soort(genre):
    """house, hiphop of anders."""
    g = (genre or "").lower()
    if any(h in g for h in HIPHOP):
        return "hiphop"
    if any(h in g for h in HOUSE):
        return "house"
    return "anders"


def energie_uit_volume(volume):
    """Het volume dat ik een track in de set gaf is mijn energie-inschatting:
    17 is achtergrond, 33 is vol gas. Vertaal dat naar 1 tot 5."""
    if not volume:
        return 3
    return max(1, min(5, round((volume - 16) / 3.6)))


def zoek_kandidaten(query, country="NL", limit=8):
    """Meerdere treffers, gesorteerd op hoe goed ze passen. Voor de UI, waar
    jij zelf de juiste versie aanwijst in plaats van dat ik gok."""
    results = _search(query, country)
    # de UI mag losser zijn dan resolve_info, jij kiest immers zelf. Maar
    # resultaten die nergens op slaan hoeven niet in de lijst.
    gescoord = [x for x in results if _score(x, query) >= 1.5]
    gescoord.sort(key=lambda x: _score(x, query), reverse=True)
    uit = []
    for x in gescoord[:limit]:
        uit.append({
            "url": x["trackViewUrl"],
            "label": f"{x['artistName']} - {x['trackName']}",
            "art": x.get("artworkUrl100", "").replace("100x100", "200x200"),
            "album": x.get("collectionName", ""),
            "genre": x.get("primaryGenreName", ""),
            "preview": x.get("previewUrl", ""),
            "artiest": x.get("artistName", ""),
            "score": round(_score(x, query), 2),
        })
    return uit


def tracks_van(artiest, country="NL", limit=14):
    """Alles wat deze artiest heeft, om nieuwe nummers mee voor te stellen."""
    uit = []
    for x in _search(artiest, country):
        namen = _artist_names(x.get("artistName", ""))
        if not any(a == _norm(artiest).strip() for a in namen):
            continue
        if JUNK.search(x.get("trackName", "") + " " + x.get("collectionName", "")):
            continue
        uit.append({
            "url": x["trackViewUrl"],
            "label": f"{x['artistName']} - {x['trackName']}",
            "art": x.get("artworkUrl100", "").replace("100x100", "300x300"),
            "genre": x.get("primaryGenreName", ""),
            "preview": x.get("previewUrl", ""),
            "artiest": x.get("artistName", ""),
            "duur": round((x.get("trackTimeMillis") or 0) / 1000),
        })
    return uit[:limit]


def bewaar_setlist(data):
    """Schrijft setlist.json terug, zonder de velden die alleen intern zijn."""
    schoon = {k: v for k, v in data.items() if not k.startswith("_intern")}
    SETLIST.write_text(
        json.dumps(schoon, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------- Sonos

def speakers():
    """SSDP-discovery, met een subnet-scan als de firewall multicast blokkeert."""
    found = soco.discover(timeout=8)
    if not found:
        print("(geen antwoord op discovery, ik scan het netwerk af...)")
        found = soco.discovery.scan_network(multi_household=False, max_threads=200)
    return sorted(found or set(), key=lambda s: s.player_name)


def _los(speaker):
    """Haal de speaker uit zijn groep, anders speelt je hele huis mee."""
    try:
        if len(speaker.group.members) > 1:
            speaker.unjoin()
    except Exception:
        pass
    return speaker


def pick(name=None, ip=None, los=True):
    if ip:
        s = soco.SoCo(ip)
        return _los(s) if los else s.group.coordinator
    found = speakers()
    if not found:
        sys.exit(
            "Geen Sonos gevonden. Check of deze pc op hetzelfde wifi zit als de "
            "speaker. Lukt het niet, zet dan het IP-adres in setlist.json als "
            '"speaker_ip" (staat in de Sonos-app bij Instellingen > Systeem > '
            "je product > Over)."
        )
    if name:
        for s in found:
            if s.player_name.lower() == name.lower():
                return _los(s) if los else s.group.coordinator
        sys.exit(
            f"Speaker '{name}' niet gevonden. Wel gevonden: "
            + ", ".join(s.player_name for s in found)
        )
    eerste = found[0]
    return _los(eerste) if los else eerste.group.coordinator


def _seconds(stamp):
    """"0:03:21" -> 201. Geeft 0 als Sonos niks zinnigs teruggeeft."""
    try:
        parts = [int(p) for p in stamp.split(":")]
    except (ValueError, AttributeError):
        return 0
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def fade_to(speaker, target, seconds=2.0):
    """Glij naar een volume in plaats van er hard heen te springen."""
    current = speaker.volume
    if current == target:
        return
    steps = max(abs(target - current), 1)
    delay = seconds / steps
    direction = 1 if target > current else -1
    for _ in range(steps):
        current += direction
        speaker.volume = current
        time.sleep(delay)


# ---------------------------------------------------------------- setlist

def load_setlist():
    data = json.loads(SETLIST.read_text(encoding="utf-8"))
    data.setdefault("speaker", None)
    data.setdefault("speaker_ip", None)
    data.setdefault("volume", 25)
    data.setdefault("crossfade", True)
    data.setdefault("country", "NL")
    data.setdefault("tracks", [])
    return data


def resolve_tracks(data, verbose=True):
    out = []
    for i, t in enumerate(data["tracks"], 1):
        if isinstance(t, str):
            t = {"q": t}
        if t.get("url"):
            hit = {
                "url": t["url"],
                "label": t.get("label") or t.get("q") or t["url"],
                "art": t.get("art", ""),
                "genre": t.get("genre", ""),
            }
        else:
            hit = resolve_info(t["q"], data["country"])
        if not hit:
            if verbose:
                print(f"  {i:2}. NIET GEVONDEN: {t['q']}")
            continue
        entry = {
            "url": hit["url"],
            "label": hit["label"],
            "art": hit.get("art", ""),
            "genre": hit.get("genre", ""),
            "duur": hit.get("duur", 0),
            "soort": soort(hit.get("genre", "")),
            "energie": t.get("energie") or energie_uit_volume(t.get("volume")),
            "volume": t.get("volume"),
            "cut": t.get("cut"),
        }
        out.append(entry)
        if verbose:
            note = f"   ({t['note']})" if t.get("note") else ""
            print(f"  {i:2}. {entry['label']}{note}")
    return out


# ---------------------------------------------------------------- commands

def cmd_speakers():
    for s in speakers():
        grouped = "" if len(s.group.members) == 1 else f"  [groep: {s.group.label}]"
        print(f"{s.player_name}  ({s.ip_address}){grouped}")


def cmd_check():
    data = load_setlist()
    print(f"Speaker : {data['speaker'] or '(eerste die ik vind)'}")
    print(f"Volume  : {data['volume']}   crossfade: {data['crossfade']}")
    print(f"Set     : {len(data['tracks'])} tracks\n")
    tracks = resolve_tracks(data)
    print(f"\n{len(tracks)}/{len(data['tracks'])} tracks gevonden op Apple Music.")


def cmd_live():
    data = load_setlist()
    speaker = pick(data["speaker"], data["speaker_ip"])
    share = ShareLinkPlugin(speaker)

    print(f"Draaien op: {speaker.player_name}\n")
    tracks = resolve_tracks(data)
    if not tracks:
        sys.exit("Lege setlist.")

    speaker.clear_queue()
    try:
        speaker.cross_fade = bool(data["crossfade"])
    except Exception as exc:  # niet elke bron accepteert dit
        print(f"(crossfade kon niet aan: {exc})")

    speaker.volume = 0
    for t in tracks:
        share.add_share_link_to_queue(t["url"])
    speaker.play_from_queue(0)
    fade_to(speaker, data["volume"], seconds=4)

    queued = len(tracks)
    stamp = SETLIST.stat().st_mtime
    last_track = None
    cut_done = set()
    print("\nDraait. Ctrl+C om te stoppen. setlist.json mag je nu live aanpassen.\n")

    try:
        while True:
            time.sleep(2)

            # setlist aangepast? nieuwe tracks bijqueuen zonder te onderbreken
            now = SETLIST.stat().st_mtime
            if now != stamp:
                stamp = now
                try:
                    data = load_setlist()
                    fresh = resolve_tracks(data, verbose=False)
                except Exception as exc:
                    print(f"setlist.json niet leesbaar: {exc}")
                    continue
                for t in fresh[queued:]:
                    share.add_share_link_to_queue(t["url"])
                    print(f"  + bijgequeued: {t['label']}")
                if len(fresh) > queued:
                    tracks = fresh
                    queued = len(fresh)

            info = speaker.get_current_track_info()
            current = (info.get("title") or "").strip()
            if current and current != last_track:
                last_track = current
                pos = int(info.get("playlist_position") or 0)
                print(f"NU: {info.get('artist', '')} - {current}")
                if 0 < pos <= len(tracks):
                    want = tracks[pos - 1].get("volume")
                    if want:
                        fade_to(speaker, want, seconds=3)

            # afkappen: de laatste seconden van een track overslaan met een
            # volumedip eroverheen, zodat de overgang niet als een knip klinkt
            if 0 < pos <= len(tracks) and pos not in cut_done:
                cut = tracks[pos - 1].get("cut")
                rest = _seconds(info.get("duration")) - _seconds(info.get("position"))
                if cut and 0 < rest <= cut:
                    cut_done.add(pos)
                    here = speaker.volume
                    fade_to(speaker, max(here - 8, 0), seconds=1.5)
                    speaker.next()
                    fade_to(speaker, here, seconds=1.5)
    except KeyboardInterrupt:
        print("\nUitfaden...")
        fade_to(speaker, 0, seconds=4)
        speaker.pause()
        speaker.volume = data["volume"]
        print("Gestopt.")


def cmd_next():
    d = load_setlist()
    speaker = pick(d["speaker"], d["speaker_ip"])
    speaker.next()
    time.sleep(1)
    info = speaker.get_current_track_info()
    print(f"NU: {info.get('artist', '')} - {info.get('title', '')}")


def cmd_vol(value):
    d = load_setlist()
    speaker = pick(d["speaker"], d["speaker_ip"])
    fade_to(speaker, int(value), seconds=2)
    print(f"Volume {speaker.volume}")


def cmd_stop():
    d = load_setlist()
    speaker = pick(d["speaker"], d["speaker_ip"])
    fade_to(speaker, 0, seconds=3)
    speaker.pause()
    speaker.clear_queue()
    print("Gestopt en queue leeg.")


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "check"
    if cmd == "speakers":
        cmd_speakers()
    elif cmd == "check":
        cmd_check()
    elif cmd == "live":
        cmd_live()
    elif cmd in ("ui", "web"):
        import server
        server.run()
    elif cmd == "next":
        cmd_next()
    elif cmd == "vol":
        cmd_vol(args[1])
    elif cmd == "stop":
        cmd_stop()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
