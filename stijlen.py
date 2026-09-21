"""Welke nummers zijn house en welke Nederlandse hiphop.

Het genre uit de catalogus is daar niet betrouwbaar genoeg voor: Apple zet
sommige Nederlandse tracks onder Pop of R&B, en die stonden dan niet bij de
hiphop. Daarom eerst een indeling op artiest, en pas daarna op het genre.

De artiesten staan per substijl gegroepeerd. Dat is puur om de lijst
leesbaar te houden en om er later fijner op te kunnen indelen; in de
interface zie je House en Nederlandse hiphop.

Klopt een nummer niet, dan zet je het in de Setlist-tab bij de andere groep.
Die keuze komt in setlist.json en gaat hier altijd voor.
"""

# de naam die je in de interface ziet, en wie erin thuishoort
STIJLEN = {
    "tech-house": ("Tech house", [
        "dom dolla", "fisher", "chris lake", "mau p", "ki/ki", "jordan peak",
        "cloonee", "solardo", "patrick topping", "dombresky", "crusy",
        "franky rizardo", "john summit", "eli brown", "odd mob", "joshwa",
        "mr. belt & wezol", "enzo is burning", "michael bibi", "ruze",
        "hannah laing", "omnom", "alexis roberts",
    ]),
    "vocal-house": ("Vocal house", [
        "mk", "chrystal", "sonny fodera", "clementine douglas", "gorgon city",
        "meduza", "goodboys", "vintage culture", "jack marlow", "mohtiv",
        "kisch", "ferra black", "jayc", "christo", "hugel", "endor",
        "james hype", "joy anonymous", "warren blake", "jazzy", "d.o.d",
        "francis mercier", "diplo", "topic", "arash", "solto", "david guetta",
        "kris kross amsterdam", "tsha", "syon", "maverick sabre",
    ]),
    "garage": ("UK garage en bass", [
        "sammy virji", "interplanetary criminal", "silva bumpa", "borai",
        "denham audio", "hamdi", "skream", "conducta", "main phase", "salute",
        "eliza rose", "overmono", "piri & tommy", "piri", "tommy",
    ]),
    "melodic": ("Melodic en deep house", [
        "ben böhmer", "ben bohmer", "lane 8", "maribou state", "rüfüs du sol",
        "rufus du sol", "bicep", "bonobo", "barry can't swim", "anotr",
        "abel balder", "cassian", "dj seinfeld", "ross from friends",
        "nightmares on wax", "kolter", "chris stussy", "nils hoffmann",
        "holly walker", "jungle", "parcels",
    ]),
    "organic": ("Organic en afro house", [
        "keinemusik", "&me", "rampa", "adam port", "black coffee", "bedouin",
        "innellea", "massano", "argy", "monolink", "jan blomqvist", "satori",
        "themba", "caiiro", "nitefreak", "trikk", "anyma", "stryv", "chuala",
        "omnya", "baset", "alan dixon", "malachiii", "bondi", "ami faku",
        "emmanuel jal", "dixon", "ame", "adriatique", "mathame", "tale of us",
        "stephan bodzin", "da capo", "moojo", "sun-el musician", "shimza",
        "kerala dust", "jimi jules", "colyn", "yotto", "marsh",
        "agents of time", "fideles", "kevin de vries", "whomadewho",
        "emmit fenn", "lyke", "eli & fur", "leo wood", "kasango", "ar/co",
        "rebuke", "rebūke", "son of son",
    ]),
    "dnb": ("Drum and bass", [
        "sub focus", "dimension", "nia archives", "skrillex", "four tet",
        "fred again..", "fred again",
    ]),
    "klassiek": ("Klassieke house", [
        "celeda", "danny tenaglia", "dennis ferrer", "green velvet",
        "armand van helden", "todd terry", "mason", "nightcrawlers",
        "disclosure",
    ]),
    "nl-hiphop": ("Nederlandse hiphop", [
        "$hirak", "adje", "aliyah", "sbmg", "bokoesam", "broederliefde",
        "chivv", "dio", "jayh", "dopebwoy", "equalz", "frenna", "fresku",
        "henkie t", "la$$a", "idaly", "jacin trill", "jonna fraser",
        "josylvio", "kempi", "kraantje pappie", "tabitha", "marone", "ares",
        "d-double", "milolaathetlukken", "ronnie flex", "mr. polska",
        "sevn alias", "sor", "typhoon", "winne", "boef", "jairzinho",
        "yung felix", "philly moré", "antoon",
    ]),
    "soul": ("Soul en rest", [
        "jordan rakei", "tom misch", "de la soul", "amadou", "mariam",
    ]),
}

# de fijne indeling hierboven bepaalt alleen waar een artiest thuishoort; in
# de interface zie je twee groepen, want dat is hoe je je set bekijkt
HOUSE_STIJLEN = {"tech-house", "vocal-house", "garage", "melodic", "dnb",
                 "klassiek", "organic"}

VOLGORDE = ["house", "nl-hiphop", "overig"]
NAMEN = {
    "house": "House",
    "nl-hiphop": "Nederlandse hiphop",
    "overig": "Rest",
}

# artiestnaam (klein) -> stijlsleutel, voor een snelle opzoeking
_VAN_ARTIEST = {}
for _sleutel, (_naam, _artiesten) in STIJLEN.items():
    for _a in _artiesten:
        _VAN_ARTIEST[_a] = _sleutel


def stijl_van(label, genre=""):
    """House of Nederlandse hiphop. Eerst op artiest, want Apple zet
    Nederlandse tracks soms onder Pop of R&B en dan staan ze bij de verkeerde
    groep. Pas als de artiest onbekend is telt het genre uit de catalogus."""
    artiest = (label or "").split(" - ")[0].lower()

    gevonden = _VAN_ARTIEST.get(artiest)
    if not gevonden:
        for naam, sleutel in _VAN_ARTIEST.items():
            if naam in artiest:
                gevonden = sleutel
                break
    if gevonden:
        if gevonden in HOUSE_STIJLEN:
            return "house"
        if gevonden == "nl-hiphop":
            return "nl-hiphop"
        return "overig"

    g = (genre or "").lower()
    if any(h in g for h in ("hiphop", "hip-hop", "rap")):
        return "nl-hiphop"
    if any(h in g for h in ("dance", "house", "elektronisch", "electronic",
                            "techno", "dubstep", "garage")):
        return "house"
    return "overig"


def keuzes():
    """Voor het keuzemenu in de interface."""
    return [{"sleutel": s, "naam": NAMEN[s]} for s in VOLGORDE]
