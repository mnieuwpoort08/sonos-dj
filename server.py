"""Webinterface voor de Sonos DJ: alles vanuit een pagina op je telefoon of pc.

    python dj.py ui

Draait lokaal. Je Sonos heeft geen account of sleutel nodig, de speaker praat
gewoon over je eigen wifi. Apple Music moet eenmalig in de Sonos-app gekoppeld
zijn, dat kan alleen daar.
"""

import ctypes
import json
import secrets
import math
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import soco
from soco.plugins.sharelink import ShareLinkPlugin

import dj

HERE = Path(__file__).parent
SMAAK = HERE / "smaak.json"
DROPS = HERE / "drops.json"
UI = HERE / "ui.html"

PORT = 8765
VOORUIT = 5
NIET_HERHALEN = 12
LIKE_FACTOR = 2.0
MAX_GEWICHT = 8.0

# artiesten die passen bij wat er al in de set zit, als voer voor de proefbak
VERWANT = [
    "Sammy Virji", "Chris Stussy", "PAWSA", "Cloonee", "Kettama", "Salute",
    "Mall Grab", "Hannah Laing", "Joshwa", "Sonny Fodera", "Gorgon City",
    "Solardo", "Patrick Topping", "James Hype", "Vintage Culture", "MEDUZA",
    "Endor", "Dennis Ferrer", "Green Velvet", "Eliza Rose", "Overmono",
    "Barry Can't Swim", "ANOTR", "Kolter", "Franky Rizardo", "Jordan Peak",
    "Silva Bumpa", "Dombresky", "Crusy", "Mau P", "Mr. Belt & Wezol",
    "Dam Swindle", "Detlef", "Latmun", "Kevin de Vries", "Argy", "Chris Lake",
    "John Summit", "FISHER", "Hugel", "Clementine Douglas", "CHRYSTAL",
    "Jonna Fraser", "Broederliefde", "Ronnie Flex", "Frenna", "Henkie T",
    "Equalz", "$hirak", "Sevn Alias", "Josylvio", "Boef", "Lijpe", "Idaly",
    "Chivv", "Bryan Mg", "Dopebwoy", "Jayh", "Young Ellens", "Hef",
    "Bokoesam", "Qlas & Blacka", "Antoon", "Kraantje Pappie", "Ares",
]

# standen die je vaker nodig hebt dan drie schuiven verzetten
PRESETS = {
    "huiswerk": {"house": 0.55, "energie": 2.0, "spreiding": 1.0,
                 "uitleg": "rustig op de achtergrond"},
    "opwarmen": {"house": 0.3, "energie": 3.0, "spreiding": 1.5,
                 "uitleg": "veel Nederlands, nog niet te hard"},
    "volgas": {"house": 0.8, "energie": 4.5, "spreiding": 1.1,
               "uitleg": "house op volle sterkte"},
    "verrassen": {"house": 0.5, "energie": 3.0, "spreiding": 3.0,
                  "uitleg": "alles door elkaar"},
}

MAX_PER_ARTIEST = 3   # zoveel nummers van dezelfde naam in een proefstapel

QUEUE_MAX = 40        # zoveel afgespeelde nummers houden we hooguit vast
QUEUE_HOUD = 12       # zoveel blijven er achter de huidige staan

DROP_PLUS = 6        # hoeveel harder tijdens een drop
DROP_DUUR = 32       # seconden dat het hoger blijft
DROP_MARGE = 2.5     # hoe dicht bij het moment we mogen zitten
MAX_VOLUME = 45      # harde bovengrens, wat er verder ook gebeurt


def wakker_houden(aan):
    """Zolang er muziek draait mag Windows niet in slaap vallen, anders valt de
    set stil. Het scherm mag wel uit."""
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    try:
        vlaggen = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if aan else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(vlaggen)
        return True
    except (AttributeError, OSError):
        return False          # geen Windows, dan regelt het besturingssysteem het


class DJ:
    """Alle staat van de sessie: speaker, pool, smaak en mood."""

    def __init__(self):
        self.speaker = None
        self.share = None
        self.pool = []
        self.per_soort = {}
        self.smaak = self._laad_smaak()
        self.mood = {"house": 0.75, "energie": 3.0, "spreiding": 1.2}
        self.recent = []
        self.op_positie = {}
        self.modus = "uit"          # uit | set | shuffle
        self.lock = threading.Lock()
        self.motor = None
        self.fout = None
        self.drops = self._laad_drops()
        # standaard uit: een volumesprong die je niet verwacht is vervelender
        # dan geen volumesprong
        self.drops_aan = bool(dj.load_setlist().get("drops_aan", False))
        self.basisvolume = 20
        self.drop_tot = 0
        self.cut_gedaan = set()
        self.storingen = 0
        self.gebruikte_bronnen = []      # artiesten die de proefbak al gehad heeft
        self.opbouw = {"aan": False, "van": 2.0, "naar": 5.0, "minuten": 90}
        self.begonnen = 0

    # -------------------------------------------------------- smaak

    def _laad_smaak(self):
        if SMAAK.exists():
            try:
                return json.loads(SMAAK.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _bewaar_smaak(self):
        SMAAK.write_text(
            json.dumps(self.smaak, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def smaakgewicht(self, track):
        return self.smaak.get(track["url"], {}).get("gewicht", 1.0)

    def oordeel(self, url, leuk):
        track = next((t for t in self.pool if t["url"] == url), None)
        if not track:
            return None
        entry = self.smaak.setdefault(url, {"label": track["label"]})
        entry["gewicht"] = (
            min(self.smaakgewicht(track) * LIKE_FACTOR, MAX_GEWICHT) if leuk else 0.0
        )
        entry["label"] = track["label"]
        self._bewaar_smaak()
        return entry["gewicht"]

    def haal_uit_queue(self, url):
        """Een weggeveegd nummer staat meestal al verderop in de wachtrij.
        Zonder dit komt hij alsnog voorbij, en dat voelt als niet luisteren.
        Van achter naar voren verwijderen, want indexen schuiven op."""
        if not self.speaker:
            return 0
        try:
            huidig = int(self.speaker.get_current_track_info()
                         .get("playlist_position") or 0)
        except Exception:
            return 0

        with self.lock:
            later = sorted((pos for pos, t in self.op_positie.items()
                            if pos > huidig and t["url"] == url), reverse=True)
        weg = 0
        for pos in later:
            try:
                self.speaker.remove_from_queue(pos - 1)   # soco telt vanaf 0
                weg += 1
            except Exception as exc:
                self.fout = f"uit queue halen mislukte: {exc}"
                continue
            with self.lock:
                self.op_positie.pop(pos, None)
                # alles daarachter schuift een plek op
                verschoven = {(k - 1 if k > pos else k): v
                              for k, v in self.op_positie.items()}
                self.op_positie = verschoven
        return weg

    def herplan(self):
        """Gooit alles weg wat nog niet gespeeld is en vult opnieuw. Zo werkt
        een nieuwe mood meteen door in plaats van pas over vijf nummers."""
        if not self.speaker or self.modus != "shuffle":
            return 0
        try:
            huidig = int(self.speaker.get_current_track_info()
                         .get("playlist_position") or 0)
        except Exception:
            return 0

        with self.lock:
            later = sorted((p for p in self.op_positie if p > huidig), reverse=True)
        for pos in later:
            try:
                self.speaker.remove_from_queue(pos - 1)
            except Exception as exc:
                self.fout = f"herplannen: {exc}"
                break
            with self.lock:
                self.op_positie.pop(pos, None)

        for _ in range(VOORUIT):
            self.queue_bij()
        return len(later)

    def vergeet(self, url=None):
        if url:
            self.smaak.pop(url, None)
        else:
            self.smaak = {}
        self._bewaar_smaak()

    # -------------------------------------------------------- drops

    def _laad_drops(self):
        if DROPS.exists():
            try:
                return json.loads(DROPS.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _tijden(self, url):
        """Oud formaat was een kale lijst, nieuw formaat heeft een bron erbij."""
        d = self.drops.get(url)
        if isinstance(d, list):
            return d
        return (d or {}).get("tijden", [])

    def _bron(self, url):
        d = self.drops.get(url)
        return "jij" if isinstance(d, list) else (d or {}).get("bron", "jij")

    def _bewaar_drops(self):
        DROPS.write_text(
            json.dumps(self.drops, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def markeer_drop(self, url, seconde):
        """Jij hoort de drop, ik niet. Deze knop is mijn oren. Wat jij aanwijst
        vervangt altijd een schatting."""
        tijden = [] if self._bron(url) == "schatting" else list(self._tijden(url))
        if not any(abs(t - seconde) < 5 for t in tijden):
            tijden.append(round(seconde))
            tijden.sort()
        self.drops[url] = {"tijden": tijden, "bron": "jij"}
        self._bewaar_drops()
        return tijden

    def schat_drops(self):
        """Bij house zit de eerste drop meestal rond een vijfde van de track.
        Dit is een gok, geen waarneming: zodra jij zelf markeert vervalt hij."""
        gezet = 0
        for t in self.pool:
            if self._tijden(t["url"]):
                continue
            duur = t.get("duur") or 0
            if duur < 90:
                continue
            deel = 0.22 if t.get("soort") == "house" else 0.3
            self.drops[t["url"]] = {
                "tijden": [round(duur * deel)], "bron": "schatting",
            }
            gezet += 1
        self._bewaar_drops()
        return gezet

    def wis_drops(self, url=None):
        if url:
            self.drops.pop(url, None)
        else:
            self.drops = {}
        self._bewaar_drops()

    # -------------------------------------------------------- mood

    def moodgewicht(self, track):
        """Hoe goed past deze track bij de schuiven die je hebt gezet."""
        deel = self.mood["house"]
        if track["soort"] == "house":
            stijl = deel
        elif track["soort"] == "hiphop":
            stijl = 1.0 - deel
        else:
            stijl = 0.5
        stijl = 0.05 + 0.95 * stijl        # nooit helemaal nul, anders valt alles weg
        # delen door het aantal nummers van die soort, anders wint house altijd
        # omdat er nu eenmaal meer van in de set zit; de fader moet de
        # verhouding bepalen, niet de toevallige samenstelling
        stijl /= max(self.per_soort.get(track["soort"], 1), 1)

        afstand = track["energie"] - self.mood["energie"]
        energie = math.exp(-(afstand ** 2) / (2 * self.mood["spreiding"] ** 2))
        return stijl * max(energie, 0.02)

    def gewicht(self, track):
        return self.smaakgewicht(track) * self.moodgewicht(track)

    def _doe_opbouw(self):
        """Een avond begint rustig en loopt op. Zolang dit aan staat schuift de
        energiefader vanzelf mee, van `van` naar `naar` over de ingestelde tijd,
        en blijft daarna op dat niveau."""
        if not self.opbouw["aan"] or not self.begonnen:
            return
        minuten = max(self.opbouw["minuten"], 1)
        deel = min((time.time() - self.begonnen) / (minuten * 60), 1.0)
        van, naar = self.opbouw["van"], self.opbouw["naar"]
        self.mood["energie"] = round(van + (naar - van) * deel, 2)

    def opbouw_stand(self):
        """Hoe ver de avond is, voor in de interface."""
        if not self.opbouw["aan"] or not self.begonnen:
            return None
        minuten = max(self.opbouw["minuten"], 1)
        verstreken = (time.time() - self.begonnen) / 60
        return {
            "minuten": round(verstreken),
            "van": minuten,
            "klaar": verstreken >= minuten,
            "energie": self.mood["energie"],
        }

    # -------------------------------------------------------- pool

    def laad_pool(self):
        data = dj.load_setlist()
        self.pool = dj.resolve_tracks(data, verbose=False)
        self.per_soort = {}
        for t in self.pool:
            self.per_soort[t["soort"]] = self.per_soort.get(t["soort"], 0) + 1
        return self.pool

    def verbind(self, naam=None, ip=None):
        data = dj.load_setlist()
        self.speaker = dj.pick(naam or data["speaker"], ip or data["speaker_ip"])
        self.share = ShareLinkPlugin(self.speaker)
        if naam:
            data["speaker"] = naam
            data["speaker_ip"] = None
            dj.bewaar_setlist(data)
        return self.speaker

    # -------------------------------------------------------- draaien

    def kies(self):
        kandidaten = [
            t for t in self.pool
            if self.gewicht(t) > 0 and t["url"] not in self.recent
        ]
        if not kandidaten:
            kandidaten = [t for t in self.pool if self.gewicht(t) > 0]
        if not kandidaten:
            return None
        keuze = random.choices(
            kandidaten, weights=[self.gewicht(t) for t in kandidaten], k=1
        )[0]
        self.recent.append(keuze["url"])
        del self.recent[:-NIET_HERHALEN]
        return keuze

    def _queue_lengte(self):
        """De echte lengte van de wachtrij. add_share_link_to_queue geeft een
        positie terug die er soms naast zit (1, 2, 2, 2 bij vier nummers), en
        dan hangt het verkeerde nummer aan je like of je drop."""
        try:
            return self.speaker.get_queue(0, 1).total_matches
        except Exception as exc:
            self.fout = f"wachtrijlengte opvragen mislukte: {exc}"
            return 0

    def queue_bij(self):
        track = self.kies()
        if not track:
            return None
        self.share.add_share_link_to_queue(track["url"])
        positie = self._queue_lengte()
        if positie:
            with self.lock:
                self.op_positie[positie] = track
        return track

    def start_shuffle(self, volume):
        self.modus = "shuffle"
        self.begonnen = time.time()
        if self.opbouw["aan"]:
            self.mood["energie"] = self.opbouw["van"]
        self.recent, self.op_positie, self.cut_gedaan = [], {}, set()
        self.speaker.clear_queue()
        self._crossfade(True)
        self.speaker.volume = 0
        for _ in range(VOORUIT + 1):
            self.queue_bij()
        self.speaker.play_from_queue(0)
        self._zet_volume(volume)
        wakker_houden(True)
        self._start_motor()

    def start_set(self, volume):
        """De setlist op volgorde, zoals hij is opgeschreven."""
        self.modus = "set"
        self.op_positie, self.cut_gedaan = {}, set()
        self.speaker.clear_queue()
        self._crossfade(True)
        self.speaker.volume = 0
        for track in self.pool:
            self.share.add_share_link_to_queue(track["url"])
            positie = self._queue_lengte()
            if positie:
                self.op_positie[positie] = track
        self.speaker.play_from_queue(0)
        self._zet_volume(volume)
        self._start_motor()

    def _zet_volume(self, volume):
        """Faden en daarna nameten. Een speaker die net uit een groep komt kan
        zijn eigen oude volume terugpakken, en dat wil je niet ontdekken door
        het te horen."""
        volume = max(0, min(int(volume), MAX_VOLUME))
        self.basisvolume = volume
        self.drop_tot = 0
        dj.fade_to(self.speaker, volume, seconds=4)
        time.sleep(1)
        if abs(self.speaker.volume - volume) > 1:
            self.fout = (f"speaker sprong naar {self.speaker.volume}, "
                         f"teruggezet op {volume}")
            self.speaker.volume = volume

    def _crossfade(self, aan):
        try:
            self.speaker.cross_fade = aan
        except Exception as exc:
            self.fout = f"crossfade kon niet aan: {exc}"

    def _start_motor(self):
        if self.motor and self.motor.is_alive():
            return
        self.motor = threading.Thread(target=self._loop, daemon=True)
        self.motor.start()

    def _loop(self):
        """Vult de shuffle-queue bij en past het volume aan per track."""
        vorige = None
        while True:
            time.sleep(3)
            if self.modus == "uit" or not self.speaker:
                continue
            try:
                info = self.speaker.get_current_track_info()
                positie = int(info.get("playlist_position") or 0)

                if self.modus == "shuffle":
                    with self.lock:
                        hoogste = max(self.op_positie) if self.op_positie else 0
                    if hoogste - positie < VOORUIT:
                        self.queue_bij()

                if self.modus == "set" and positie != vorige:
                    vorige = positie
                    track = self.op_positie.get(positie)
                    if track and track.get("volume"):
                        self.basisvolume = track["volume"]
                        dj.fade_to(self.speaker, track["volume"], seconds=3)

                self._doe_opbouw()
                self._doe_drops(info, positie)
                self._doe_cut(info, positie)
                self._ruim_queue_op(positie)
                self.storingen = 0
                self.fout = None
            except Exception as exc:
                self.fout = f"achtergrondlus: {exc}"
                self._herstel(exc)

    def _doe_drops(self, info, positie):
        """Zet het volume op bij een gemarkeerde drop en weer terug erna."""
        if not self.drops_aan:
            if self.drop_tot:                     # net uitgezet tijdens een drop
                self.drop_tot = 0
                dj.fade_to(self.speaker, self.basisvolume, seconds=3)
            return
        track = self.op_positie.get(positie)
        nu = time.time()

        if self.drop_tot and nu >= self.drop_tot:
            self.drop_tot = 0
            dj.fade_to(self.speaker, self.basisvolume, seconds=4)
            return
        if self.drop_tot or not track:
            return

        momenten = self._tijden(track["url"])
        if not momenten:
            return
        seconden = dj._seconds(info.get("position"))
        if any(abs(seconden - m) <= DROP_MARGE for m in momenten):
            doel = min(self.basisvolume + DROP_PLUS, MAX_VOLUME)
            self.drop_tot = nu + DROP_DUUR
            dj.fade_to(self.speaker, doel, seconds=1.2)

    def _doe_cut(self, info, positie):
        """Sla de laatste seconden van een nummer over, met een volumedip over
        de knip heen. Stond alleen in de terminalversie, hoort hier ook."""
        track = self.op_positie.get(positie)
        if not track or positie in self.cut_gedaan:
            return
        cut = track.get("cut")
        if not cut:
            return
        rest = dj._seconds(info.get("duration")) - dj._seconds(info.get("position"))
        if 0 < rest <= cut:
            self.cut_gedaan.add(positie)
            hier = self.speaker.volume
            dj.fade_to(self.speaker, max(hier - 8, 0), seconds=1.5)
            self.speaker.next()
            dj.fade_to(self.speaker, hier, seconds=1.5)

    def _ruim_queue_op(self, positie):
        """In shuffle groeit de wachtrij eindeloos. Wat allang gespeeld is mag
        weg, anders wordt elke toevoeging trager."""
        if self.modus != "shuffle" or positie <= QUEUE_MAX:
            return
        weg = positie - QUEUE_HOUD
        for _ in range(weg):
            try:
                self.speaker.remove_from_queue(0)
            except Exception as exc:
                self.fout = f"opruimen: {exc}"
                return
        with self.lock:
            self.op_positie = {k - weg: v for k, v in self.op_positie.items()
                               if k - weg > 0}
        self.cut_gedaan = {k - weg for k in self.cut_gedaan if k - weg > 0}

    def _herstel(self, exc):
        """Speaker uit of even van de wifi: opnieuw verbinden in plaats van
        eindeloos dezelfde fout herhalen."""
        self.storingen += 1
        if self.storingen < 3:
            return
        try:
            data = dj.load_setlist()
            self.speaker = dj.pick(data["speaker"], data["speaker_ip"])
            self.share = ShareLinkPlugin(self.speaker)
            self.storingen = 0
            self.fout = "verbinding was weg, opnieuw verbonden"
        except Exception as her:
            self.fout = f"speaker onbereikbaar: {her}"

    def stop(self, volume):
        self.modus = "uit"
        wakker_houden(False)
        if self.speaker:
            dj.fade_to(self.speaker, 0, seconds=3)
            self.speaker.pause()
            self.speaker.volume = volume

    # -------------------------------------------------------- status

    def _track_bij(self, info, positie):
        """Welk nummer speelt er echt. De administratie kan een plek
        verschuiven als de wachtrij verandert, en dan krijg je de hoes en het
        oordeel van het verkeerde nummer. Dus controleren we de naam."""
        titel = dj._norm(info.get("title") or "").strip()
        artiest = dj._norm(info.get("artist") or "").strip()
        if not titel:
            return None

        with self.lock:
            kandidaat = self.op_positie.get(positie)
        if kandidaat and titel and titel in dj._norm(kandidaat["label"]):
            return kandidaat

        # administratie klopt niet: zoek op naam in de pool
        for t in self.pool:
            plat = dj._norm(t["label"])
            if titel in plat and (not artiest or artiest.split()[0] in plat):
                with self.lock:
                    self.op_positie[positie] = t      # meteen rechtzetten
                return t
        return None

    def _uit_pool(self, titel, artiest=""):
        """Zoek een nummer in de pool op naam, voor hoes, genre en energie."""
        t_plat = dj._norm(titel or "").strip()
        a_plat = dj._norm(artiest or "").strip()
        if not t_plat:
            return None
        for t in self.pool:
            plat = dj._norm(t["label"])
            if t_plat in plat and (not a_plat or a_plat.split()[0] in plat):
                return t
        return None

    def komende(self, aantal=8):
        """Wat er na dit nummer komt, rechtstreeks uit de wachtrij van de
        speaker. Onze eigen administratie schuift mee met elke wijziging en
        klopte niet meer; de speaker weet het zeker."""
        if not self.speaker or self.modus == "uit":
            return []
        try:
            positie = int(self.speaker.get_current_track_info()
                          .get("playlist_position") or 0)
            if not positie:
                return []
            # playlist_position telt vanaf 1, get_queue vanaf 0, dus het
            # volgende nummer begint precies op index `positie`
            items = self.speaker.get_queue(positie, aantal)
        except Exception as exc:
            self.fout = f"wachtrij lezen: {exc}"
            return []

        uit = []
        for item in items:
            titel = getattr(item, "title", "") or ""
            artiest = getattr(item, "creator", "") or ""
            bekend = self._uit_pool(titel, artiest)
            uit.append({
                "label": bekend["label"] if bekend else (
                    f"{artiest} - {titel}" if artiest else titel),
                "art": (bekend or {}).get("art") or getattr(item, "album_art_uri", "") or "",
                "soort": (bekend or {}).get("soort", ""),
                "energie": (bekend or {}).get("energie"),
            })
        return uit

    def nu(self):
        if not self.speaker:
            return {"verbonden": False}
        try:
            info = self.speaker.get_current_track_info()
            staat = self.speaker.get_current_transport_info()
            positie = int(info.get("playlist_position") or 0)
            track = self._track_bij(info, positie)
            straks = self.komende(1)
            return {
                "verbonden": True,
                "volgende": straks[0]["label"] if straks else None,
                "speaker": self.speaker.player_name,
                "titel": info.get("title") or "",
                "artiest": info.get("artist") or "",
                "art": (track or {}).get("art") or info.get("album_art") or "",
                "url": (track or {}).get("url"),
                "soort": (track or {}).get("soort"),
                "energie": (track or {}).get("energie"),
                "gewicht": self.smaakgewicht(track) if track else 1.0,
                "volume": self.speaker.volume,
                "drops": len(self._tijden((track or {}).get("url"))),
                "drops_aan": self.drops_aan,
                "drops_bron": self._bron((track or {}).get("url")),
                "in_drop": bool(self.drop_tot),
                "opbouw": self.opbouw_stand(),
                "speelt": staat.get("current_transport_state") == "PLAYING",
                "modus": self.modus,
                "positie": info.get("position"),
                "duur": info.get("duration"),
                "fout": self.fout,
            }
        except Exception as exc:
            return {"verbonden": False, "fout": str(exc)}


DJ_STATE = DJ()

# lopende sessies; leeg zolang er geen code is ingesteld
SESSIES = set()


def slot_aan():
    return bool((dj.load_setlist().get("toegangscode") or "").strip())


def mag_binnen(handler):
    if not slot_aan():
        return True
    koekjes = handler.headers.get("Cookie") or ""
    for deel in koekjes.split(";"):
        naam, _, waarde = deel.strip().partition("=")
        if naam == "dj" and waarde in SESSIES:
            return True
    return False


# ---------------------------------------------------------------- api

def api_slot(body):
    """Code instellen of weghalen. Leeg betekent: geen slot."""
    data = dj.load_setlist()
    code = (body.get("code") or "").strip()
    data["toegangscode"] = code
    dj.bewaar_setlist(data)
    if not code:
        SESSIES.clear()
        return {"slot": False, "melding": "Slot eraf, iedereen op je wifi kan erbij"}
    return {"slot": True,
            "melding": "Code ingesteld. Op andere apparaten moet hij nu ingevuld."}


def api_status(_):
    data = dj.load_setlist()
    gevonden = []
    for s in dj.speakers():
        gevonden.append({
            "naam": s.player_name,
            "ip": s.ip_address,
            "groep": s.group.label if len(s.group.members) > 1 else "",
        })

    bron = dj.bron()
    spotify_uit = ""
    if bron == "spotify":
        import spotify as sp
        spotify_uit = sp.werkt()[1]

    return {
        "bron": bron,
        "bron_melding": spotify_uit,
        "speakers": gevonden,
        "gekozen": DJ_STATE.speaker.player_name if DJ_STATE.speaker else data["speaker"],
        "pool": len(DJ_STATE.pool),
        "mood": DJ_STATE.mood,
        "opbouw": DJ_STATE.opbouw,
        "drops_aan": DJ_STATE.drops_aan,
        "volume": data["volume"],
        "modus": DJ_STATE.modus,
    }


def api_verbind(body):
    DJ_STATE.verbind(body.get("naam"), body.get("ip"))
    if not DJ_STATE.pool:
        DJ_STATE.laad_pool()
    return {"ok": True, "speaker": DJ_STATE.speaker.player_name}


def api_nu_draaien(body):
    """Een nummer uit je setlijst meteen opzetten, zonder de rest te verliezen."""
    if not DJ_STATE.speaker:
        DJ_STATE.verbind()
    track = next((t for t in DJ_STATE.pool if t["url"] == body["url"]), None)
    if not track:
        return {"melding": "Nummer niet gevonden"}

    if DJ_STATE.modus == "uit":
        DJ_STATE.start_shuffle(int(body.get("volume") or dj.load_setlist()["volume"]))
        time.sleep(1)
    try:
        huidig = int(DJ_STATE.speaker.get_current_track_info()
                     .get("playlist_position") or 0)
        DJ_STATE.share.add_share_link_to_queue(track["url"], position=huidig + 1)
        with DJ_STATE.lock:
            # alles achter de invoegplek schuift een plek op
            DJ_STATE.op_positie = {
                (k + 1 if k > huidig else k): v
                for k, v in DJ_STATE.op_positie.items()
            }
            DJ_STATE.op_positie[huidig + 1] = track
        DJ_STATE.speaker.next()
    except Exception as exc:
        return {"melding": f"Lukt niet: {exc}"}
    return {"melding": f"Nu: {track['label']}"}


def api_wachtrij(_):
    """Wat er na dit nummer aankomt, gelezen uit de speaker zelf."""
    return {"rijtje": DJ_STATE.komende(8)}


def api_pool(_):
    if not DJ_STATE.pool:
        DJ_STATE.laad_pool()
    uit = []
    for t in DJ_STATE.pool:
        uit.append({
            **{k: t[k] for k in ("url", "label", "art", "soort", "energie")},
            "volume": t.get("volume"),
            "gewicht": DJ_STATE.smaakgewicht(t),
            "kans": round(DJ_STATE.gewicht(t), 3),
        })
    return {"tracks": uit}


def api_herlaad(_):
    DJ_STATE.laad_pool()
    return {"ok": True, "pool": len(DJ_STATE.pool)}


def api_mood(body):
    for sleutel in ("house", "energie", "spreiding"):
        if sleutel in body:
            DJ_STATE.mood[sleutel] = float(body[sleutel])
    vervangen = DJ_STATE.herplan()
    return {"mood": DJ_STATE.mood, "vervangen": vervangen}


def api_zoek(query):
    term = (query.get("q") or [""])[0]
    if not term.strip():
        return {"treffers": []}
    try:
        return {"treffers": dj.zoek_kandidaten(term, dj.load_setlist()["country"])}
    except Exception as exc:
        # bijvoorbeeld Spotify zonder sleutels: dat hoort een uitleg te zijn,
        # geen lege lijst of een kale serverfout
        return {"treffers": [], "melding": str(exc)}


def api_toevoegen(body):
    data = dj.load_setlist()
    if body.get("q"):
        nieuw = {"q": body["q"]}
    else:
        # alles wat we van de zoektreffer weten meenemen, anders staat er straks
        # een kale link in de set zonder naam, hoes of genre
        nieuw = {"url": body["url"]}
        for veld in ("label", "art", "genre"):
            if body.get(veld):
                nieuw[veld] = body[veld]
    if body.get("volume"):
        nieuw["volume"] = int(body["volume"])
    data["tracks"].append(nieuw)
    dj.bewaar_setlist(data)
    DJ_STATE.laad_pool()
    return {"ok": True, "pool": len(DJ_STATE.pool)}


def api_energie(body):
    """Nieuwe nummers kennen hun energie niet, dus die stel je hier zelf in."""
    data = dj.load_setlist()
    url, energie = body["url"], max(1, min(5, int(body["energie"])))
    for t in data["tracks"]:
        hit = dj.resolve_info(t["q"], data["country"]) if t.get("q") else t
        if hit and hit.get("url") == url:
            t["energie"] = energie
            dj.bewaar_setlist(data)
            DJ_STATE.laad_pool()
            return {"ok": True, "energie": energie}
    return {"ok": False, "melding": "Nummer niet gevonden in de setlist"}


def api_preset(body):
    naam = (body.get("naam") or "").lower()
    stand = PRESETS.get(naam)
    if not stand:
        return {"melding": "Die stand ken ik niet"}
    for sleutel in ("house", "energie", "spreiding"):
        DJ_STATE.mood[sleutel] = stand[sleutel]
    DJ_STATE.opbouw["aan"] = False      # een vaste stand en een oplopende avond
    vervangen = DJ_STATE.herplan()      # bijten elkaar
    return {"mood": DJ_STATE.mood, "vervangen": vervangen,
            "melding": f"{naam.capitalize()}: {stand['uitleg']}"
                       + (f", {vervangen} wachtende nummers vervangen" if vervangen else "")}


def api_opbouw(body):
    for sleutel in ("van", "naar", "minuten"):
        if sleutel in body:
            DJ_STATE.opbouw[sleutel] = float(body[sleutel])
    if "aan" in body:
        DJ_STATE.opbouw["aan"] = bool(body["aan"])
        if DJ_STATE.opbouw["aan"]:
            DJ_STATE.begonnen = time.time()
            DJ_STATE.mood["energie"] = DJ_STATE.opbouw["van"]
            DJ_STATE.herplan()
    return {"opbouw": DJ_STATE.opbouw,
            "melding": (
                f"De avond loopt van {DJ_STATE.opbouw['van']:g} naar "
                f"{DJ_STATE.opbouw['naar']:g} in "
                f"{DJ_STATE.opbouw['minuten']:g} minuten"
                if DJ_STATE.opbouw["aan"]
                else "Opbouw uit, de energiefader blijft staan waar jij hem zet")}


def api_bron(body):
    """Wisselen tussen Apple Music en Spotify. Afspelen gaat bij allebei via
    dezelfde Sonos-koppeling, alleen het zoeken verschilt."""
    keuze = "spotify" if body.get("bron") == "spotify" else "apple"
    data = dj.load_setlist()
    data["bron"] = keuze
    dj.bewaar_setlist(data)

    if keuze == "spotify":
        import spotify as sp
        ok, melding = sp.werkt()
        if not ok:
            return {"bron": keuze, "ok": False, "melding": melding}
    return {"bron": keuze, "ok": True,
            "melding": f"Zoeken gaat nu via {keuze}. Bestaande nummers blijven "
                       f"staan; die zijn al opgezocht."}


def api_bulk(body):
    """Een hele lijst in een keer, een nummer per regel. Sneller dan stuk voor
    stuk zoeken als je net begint."""
    data = dj.load_setlist()
    # op de gevonden track vergelijken, niet op de zoekterm: dezelfde plaat
    # onder een andere spelling is nog steeds dezelfde plaat
    bestaand = set()
    for t in data["tracks"]:
        hit = dj.resolve_info(t["q"], data["country"]) if t.get("q") else t
        if hit:
            bestaand.add(hit["url"])
    toegevoegd, mislukt, dubbel = [], [], []

    for regel in (body.get("tekst") or "").splitlines():
        vraag = regel.strip().strip("-").strip()
        if not vraag:
            continue
        try:
            hit = dj.resolve_info(vraag, data["country"])
        except Exception as exc:
            mislukt.append(f"{vraag} ({exc})")
            break
        if not hit:
            mislukt.append(vraag)
            continue
        if hit["url"] in bestaand:
            dubbel.append(hit["label"])
            continue
        data["tracks"].append({
            "q": vraag,
            "volume": int(body.get("volume") or data["volume"]),
        })
        bestaand.add(hit["url"])
        toegevoegd.append(hit["label"])

    dj.bewaar_setlist(data)
    DJ_STATE.laad_pool()
    return {"toegevoegd": toegevoegd, "mislukt": mislukt, "dubbel": dubbel,
            "pool": len(DJ_STATE.pool)}


def api_verwijder(body):
    data = dj.load_setlist()
    url = body.get("url")
    over = []
    for t in data["tracks"]:
        hit = dj.resolve_info(t["q"], data["country"]) if t.get("q") else t
        if hit and hit.get("url") == url:
            continue
        over.append(t)
    data["tracks"] = over
    dj.bewaar_setlist(data)
    DJ_STATE.laad_pool()
    return {"ok": True, "pool": len(DJ_STATE.pool)}


def api_start(body):
    volume = int(body.get("volume") or dj.load_setlist()["volume"])
    if not DJ_STATE.speaker:
        DJ_STATE.verbind()
    if not DJ_STATE.pool:
        DJ_STATE.laad_pool()
    if body.get("modus") == "set":
        DJ_STATE.start_set(volume)
    else:
        DJ_STATE.start_shuffle(volume)
    return {"ok": True, "modus": DJ_STATE.modus}


def api_test(_body):
    """Zet een nummer op en kijk of de speaker het echt oppakt. Dit is de enige
    betrouwbare manier om te weten of Apple Music gekoppeld is: soco's eigen
    dienstenlijst meldt Apple Music niet, ook als het gewoon werkt."""
    if not DJ_STATE.speaker:
        DJ_STATE.verbind()
    if not DJ_STATE.pool:
        DJ_STATE.laad_pool()

    sp = DJ_STATE.speaker
    was = sp.volume
    sp.clear_queue()
    sp.volume = min(was, 12)
    track = DJ_STATE.pool[0]
    try:
        DJ_STATE.share.add_share_link_to_queue(track["url"])
        sp.play_from_queue(0)
    except Exception as exc:
        sp.volume = was
        return {"ok": False, "melding": f"Speaker weigert de track: {exc}"}

    time.sleep(5)
    info = sp.get_current_track_info()
    speelt = sp.get_current_transport_info().get("current_transport_state") == "PLAYING"
    sp.pause()
    sp.volume = was
    if speelt and info.get("title"):
        return {"ok": True,
                "melding": f"Werkt. Hij speelde {info.get('artist')} - {info.get('title')}"}
    return {"ok": False,
            "melding": "Geen geluid. Staat Apple Music in de Sonos-app gekoppeld?"}


def api_stop(body):
    DJ_STATE.stop(int(body.get("volume") or dj.load_setlist()["volume"]))
    return {"ok": True}


def api_oordeel(body):
    gewicht = DJ_STATE.oordeel(body["url"], body["leuk"])
    if gewicht is None:
        return {"melding": "die track zit niet in de pool"}
    if not body["leuk"]:
        weg = DJ_STATE.haal_uit_queue(body["url"])
        try:
            if DJ_STATE.speaker:
                DJ_STATE.speaker.next()
        except Exception:
            # laatste nummer in de wachtrij, er is niets om naar door te spoelen
            pass
        extra = f" en {weg} keer uit de wachtrij gehaald" if weg else ""
        return {"melding": f"Weg, komt niet meer terug{extra}"}
    return {"melding": f"Komt nu {gewicht:g}x zo vaak langs"}


def api_drop(body):
    nu = DJ_STATE.nu()
    if not nu.get("url"):
        return {"melding": "Geen nummer herkend"}
    seconden = dj._seconds(nu.get("positie"))
    lijst = DJ_STATE.markeer_drop(nu["url"], seconden)
    m, s = divmod(int(seconden), 60)
    return {"melding": f"Drop op {m}:{s:02d} onthouden ({len(lijst)} in dit nummer)"}


def api_drop_wis(body):
    nu = DJ_STATE.nu()
    if nu.get("url"):
        DJ_STATE.wis_drops(nu["url"])
    return {"melding": "Drops van dit nummer gewist"}


def api_ontdek(query):
    """Haalt nieuwe nummers op van artiesten die bij je set passen. Wat al in
    de set zit of wat je eerder hebt afgewezen laat ik weg."""
    if not DJ_STATE.pool:
        DJ_STATE.laad_pool()
    land = dj.load_setlist()["country"]
    aantal = int((query.get("n") or ["10"])[0])

    # op naam vergelijken, want hetzelfde nummer op een ander album heeft een
    # andere link en glipte er zo alsnog doorheen
    naam = lambda t: dj._norm(t.get("label", "")).strip()
    in_pool = {t["url"] for t in DJ_STATE.pool}
    namen_in_pool = {naam(t) for t in DJ_STATE.pool}
    beoordeeld = set(DJ_STATE.smaak)
    namen_beoordeeld = {naam(v) for v in DJ_STATE.smaak.values()}
    uit_set = {t.get("artiest") or t["label"].split(" - ")[0] for t in DJ_STATE.pool}

    # artiesten die we net gehad hebben achteraan, anders krijg je drie keer
    # achter elkaar dezelfde namen voorgeschoteld
    bronnen = list(uit_set) + VERWANT
    recent = set(DJ_STATE.gebruikte_bronnen[-25:])
    vers = [a for a in bronnen if a not in recent]
    oud = [a for a in bronnen if a in recent]
    random.shuffle(vers)
    random.shuffle(oud)
    bronnen = vers + oud

    kandidaten, gezien, klacht = [], set(), None
    for artiest in bronnen:
        if len(kandidaten) >= aantal * 3:
            break
        DJ_STATE.gebruikte_bronnen.append(artiest)
        per_artiest = 0
        try:
            for t in dj.tracks_van(artiest, land):
                # hoogstens een paar per artiest, anders is je hele stapel
                # vijftien keer dezelfde naam
                if per_artiest >= MAX_PER_ARTIEST:
                    break
                if (t["url"] in in_pool or t["url"] in beoordeeld
                        or t["url"] in gezien or naam(t) in gezien
                        or naam(t) in namen_in_pool or naam(t) in namen_beoordeeld):
                    continue
                gezien.add(t["url"])
                gezien.add(naam(t))
                t["soort"] = dj.soort(t["genre"])
                kandidaten.append(t)
                per_artiest += 1
        except Exception as exc:
            DJ_STATE.fout = f"ontdekken: {exc}"
            klacht = str(exc)
            break

    del DJ_STATE.gebruikte_bronnen[:-60]
    random.shuffle(kandidaten)
    uit = {"kandidaten": kandidaten[:aantal * 3]}
    if klacht and not kandidaten:
        uit["melding"] = klacht
    return uit


def api_rotatie(body):
    """Ja zet hem in de setlist, nee zorgt dat ik hem niet meer voorstel."""
    url = body["url"]
    if not body.get("ja"):
        DJ_STATE.smaak[url] = {"label": body.get("label", url), "gewicht": 0.0}
        DJ_STATE._bewaar_smaak()
        return {"melding": "Niet in de rotatie"}

    data = dj.load_setlist()
    al_erin = False
    for t in data["tracks"]:
        hit = dj.resolve_info(t["q"], data["country"]) if t.get("q") else t
        if hit and hit.get("url") == url:
            al_erin = True
            break
    if not al_erin:
        nieuw = {"url": url}
        for veld in ("label", "art", "genre"):
            if body.get(veld):
                nieuw[veld] = body[veld]
        if body.get("volume"):
            nieuw["volume"] = int(body["volume"])
        data["tracks"].append(nieuw)
        dj.bewaar_setlist(data)

    # eerder afgewezen? dan mag dat oordeel weg
    if DJ_STATE.smaak.get(url, {}).get("gewicht") == 0:
        DJ_STATE.smaak.pop(url, None)
        DJ_STATE._bewaar_smaak()

    drop = body.get("drop")
    if drop:
        DJ_STATE.markeer_drop(url, int(drop))
    DJ_STATE.laad_pool()
    return {"melding": "In de rotatie", "pool": len(DJ_STATE.pool)}


def api_drops_aan(body):
    DJ_STATE.drops_aan = bool(body.get("aan"))
    data = dj.load_setlist()
    data["drops_aan"] = DJ_STATE.drops_aan
    dj.bewaar_setlist(data)
    return {"drops_aan": DJ_STATE.drops_aan,
            "melding": "Volume gaat omhoog bij een drop" if DJ_STATE.drops_aan
                       else "Drops staan uit, het volume blijft waar je het zet"}


def api_drops_schatten(_body):
    if not DJ_STATE.pool:
        DJ_STATE.laad_pool()
    n = DJ_STATE.schat_drops()
    return {"melding": f"{n} nummers een geschatte drop gegeven. Klopt hij niet, "
                       f"druk dan tijdens het nummer op Drop nu."}


def api_drops_alles_wissen(_body):
    DJ_STATE.wis_drops()
    return {"melding": "Alle drops gewist"}


def api_vergeet(body):
    DJ_STATE.vergeet(body.get("url"))
    return {"ok": True}


def api_smaak(_):
    uit = [
        {"url": u, "label": v.get("label", u), "gewicht": v.get("gewicht", 1.0)}
        for u, v in DJ_STATE.smaak.items()
    ]
    uit.sort(key=lambda x: -x["gewicht"])
    return {"smaak": uit}


def api_bediening(body):
    """Vorige op de eerste track, of volgende op de laatste, laat de speaker
    een fout gooien. Dat is geen crash waard."""
    sp = DJ_STATE.speaker
    if not sp:
        return {"ok": False, "melding": "Geen speaker verbonden"}
    wat = body.get("wat")
    try:
        if wat == "play":
            sp.play()
        elif wat == "pause":
            sp.pause()
        elif wat == "next":
            sp.next()
        elif wat == "prev":
            sp.previous()
        elif wat == "naar":
            seconden = int(body["waarde"])
            sp.seek(f"{seconden // 3600}:{seconden // 60 % 60:02d}:{seconden % 60:02d}")
            DJ_STATE.drop_tot = 0
        elif wat == "volume":
            DJ_STATE.basisvolume = max(0, min(int(body["waarde"]), MAX_VOLUME))
            dj.fade_to(sp, DJ_STATE.basisvolume, seconds=1)
    except Exception as exc:
        return {"ok": False, "melding": f"Dat kan nu niet: {exc}"}
    return {"ok": True}


OPEN_ROUTES = {"/api/slot-status", "/api/inloggen"}

GET_ROUTES = {
    "/api/slot-status": lambda _: {"slot": slot_aan()},
    "/api/status": api_status,
    "/api/nu": lambda _: DJ_STATE.nu(),
    "/api/pool": api_pool,
    "/api/wachtrij": api_wachtrij,
    "/api/smaak": api_smaak,
    "/api/zoek": api_zoek,
    "/api/ontdek": api_ontdek,
}

POST_ROUTES = {
    "/api/inloggen": None,      # apart afgehandeld, geeft een cookie terug
    "/api/slot": api_slot,
    "/api/verbind": api_verbind,
    "/api/mood": api_mood,
    "/api/toevoegen": api_toevoegen,
    "/api/verwijder": api_verwijder,
    "/api/energie": api_energie,
    "/api/bulk": api_bulk,
    "/api/bron": api_bron,
    "/api/opbouw": api_opbouw,
    "/api/preset": api_preset,
    "/api/nu-draaien": api_nu_draaien,
    "/api/herlaad": api_herlaad,
    "/api/start": api_start,
    "/api/stop": api_stop,
    "/api/test": api_test,
    "/api/oordeel": api_oordeel,
    "/api/vergeet": api_vergeet,
    "/api/drop": api_drop,
    "/api/drop-wis": api_drop_wis,
    "/api/rotatie": api_rotatie,
    "/api/drops-aan": api_drops_aan,
    "/api/drops-schatten": api_drops_schatten,
    "/api/drops-wissen": api_drops_alles_wissen,
    "/api/bediening": api_bediening,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _stuur(self, data, status=200, type_="application/json; charset=utf-8"):
        body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        pad = urlparse(self.path)
        if pad.path.startswith("/api/") and pad.path not in OPEN_ROUTES                 and not mag_binnen(self):
            return self._stuur({"fout": "code nodig", "slot": True}, 401)
        route = GET_ROUTES.get(pad.path)
        if route:
            try:
                return self._stuur(route(parse_qs(pad.query)))
            except Exception as exc:
                return self._stuur({"fout": str(exc)}, 500)
        return self._stuur(
            UI.read_bytes(), type_="text/html; charset=utf-8"
        )

    def do_POST(self):
        pad = urlparse(self.path).path
        lengte = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(lengte) or b"{}")

        if pad == "/api/inloggen":
            goed = (dj.load_setlist().get("toegangscode") or "").strip()
            if goed and (body.get("code") or "").strip() == goed:
                token = secrets.token_urlsafe(24)
                SESSIES.add(token)
                lijf = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header(
                    "Set-Cookie",
                    f"dj={token}; Path=/; Max-Age=2592000; SameSite=Lax",
                )
                self.send_header("Content-Length", str(len(lijf)))
                self.end_headers()
                return self.wfile.write(lijf)
            return self._stuur({"ok": False, "melding": "Code klopt niet"}, 401)

        if pad not in OPEN_ROUTES and not mag_binnen(self):
            return self._stuur({"fout": "code nodig", "slot": True}, 401)

        route = POST_ROUTES.get(pad)
        if not route:
            return self._stuur({"fout": "onbekend"}, 404)
        try:
            return self._stuur(route(body))
        except Exception as exc:
            return self._stuur({"fout": str(exc)}, 500)


def run():
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Open op deze pc:   http://localhost:{PORT}")
    print(f"Op je telefoon:    http://{ip}:{PORT}")
    print("Ctrl+C om te stoppen.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGestopt.")
