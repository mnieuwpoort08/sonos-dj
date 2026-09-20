# Sonos DJ

Een DJ voor je Sonos die luistert naar wat jij van de muziek vindt. Jij zegt welke
kant het op moet, hij kiest de nummers, regelt het volume en onthoudt je oordeel.
Bedienen doe je in de browser, ook op je telefoon.

Python + [SoCo](https://github.com/SoCo/SoCo) voor de speaker, de iTunes Search API
voor de catalogus, en een pagina zonder frameworks of buildstap.

## Hoe het werkt

Elke track in `setlist.json` wordt opgezocht in de catalogus en levert een deellink
op. Die links gaan in de wachtrij van je speaker, die ze zelf uit jouw abonnement
streamt. De audio gaat nooit via je pc.

## Apple Music of Spotify

Allebei, te kiezen in de Setup-tab. Afspelen werkt hetzelfde, mits die dienst in de
Sonos-app is gekoppeld.

- **Apple Music** is de standaard en werkt meteen: zoeken gaat via de openbare
  iTunes Search API, zonder account of sleutel.
- **Spotify** heeft voor het zoeken een gratis sleutelpaar nodig. Maak een app op
  developer.spotify.com/dashboard en zet de Client ID en het Client Secret in
  `spotify.json` naast `dj.py`, of in de omgevingsvariabelen
  `SPOTIFY_CLIENT_ID` en `SPOTIFY_CLIENT_SECRET`. Die sleutels geven alleen toegang
  tot de openbare catalogus, niet tot je eigen account of afspeellijsten.

Nummers die al in je setlist staan blijven werken als je wisselt, want die zijn al
opgezocht. Nieuwe zoekopdrachten gaan naar de gekozen bron.

## Starten

```
cd sonos-dj
.\dj.bat ui
```

Dat venster moet openblijven, want de server draait erin. Wil je dat niet, start
hem dan zonder venster:

```
start "" pythonw dj.py ui
```

De terminal geeft twee adressen: een voor deze pc en een voor je telefoon. Open dat
laatste op je telefoon, zolang die op hetzelfde wifi zit.

Eerste keer: `python -m pip install soco requests`

Bij de eerste start wordt `setlist.json` aangemaakt uit `setlist.voorbeeld.json`, een
dozijn nummers om mee te beginnen. Die gooi je eruit en vervang je door je eigen werk:
in de Setlist-tab zoek je per nummer, of je klapt daar "Of plak een hele lijst in een
keer" open en plakt er tientallen regels in. Wat je daarna via de Nieuw-tab in de
rotatie zet komt er vanzelf bij.

## Inloggen

Nergens voor nodig. De speaker praat rechtstreeks met je pc over je eigen netwerk,
zonder account, wachtwoord of sleutel. Het enige dat eenmalig moet is Apple Music
koppelen in de Sonos-app zelf, bij Instellingen, Diensten en spraak. In de Setup-tab
zit een knop die vijf seconden een nummer opzet om te controleren of dat gelukt is.

Bij het opstarten zoekt hij zelf de speaker uit `setlist.json` op en leest de set
alvast in, dus je hoeft niet elke keer naar Setup. Een bestaande Sonos-groep blijft
daarbij met rust; pas als je echt gaat afspelen wordt de box losgemaakt, zodat alleen
die ene speelt en niet je hele huis.

## De tabs

**Speler** toont wat er draait, met onder de titel welk nummer erna komt. De albumhoes is ook je swipe-kaart: naar rechts
vegen is vaker draaien, naar links is nooit meer. Op een breed scherm staat de hoes
links, de bediening in het midden en de wachtrij rechts.

**Mood** is waar je zegt wat je wilt horen. Bovenaan staan vier standen die de
schuiven in een keer goed zetten: Huiswerk (rustig op de achtergrond), Opwarmen (veel
Nederlands, nog niet te hard), Vol gas (house op volle sterkte) en Verrassen (alles
door elkaar). Daaronder schuif je zelf: hiphop tegenover house,
rustig tegenover vol gas, en hoe strak hij bij dat niveau moet blijven. Verander je
de stand, dan worden de nummers die al klaarstonden weggegooid en opnieuw gekozen,
dus het werkt meteen en niet pas over vijf nummers.

In diezelfde tab zit **Opbouw over de avond**. Staat dat aan, dan begint de shuffle
rustig en schuift de energiefader vanzelf omhoog over de tijd die je kiest, om daarna
op het hoogste niveau te blijven. Dat is wat een DJ over een avond doet, en wat een
gewone shuffle nooit doet.

**Nieuw** is de proefbak. Hij haalt nummers op van artiesten die bij je set passen,
je luistert het fragment van dertig seconden en bepaalt of hij in de rotatie komt.
Wat je afwijst wordt niet meer voorgesteld. Nummers die al in je set staan komen er
niet in, ook niet als dezelfde track op een ander album een andere link heeft.

**Setlist** is de pool, gesplitst in House en Nederlandse hiphop, met een restgroep
voor wat er niet in past. Die indeling gaat op artiest en niet op het genre van de
catalogus, want Apple zet sommige Nederlandse tracks onder Pop of R&B en dan staan ze
bij de verkeerde groep. Klopt er iets niet, kies dan onder dat nummer de andere groep;
die keuze wordt bewaard. Die groepen
klap je open en dicht, en dat onthoudt hij. Sorteren kan op de volgorde van de set,
van rustig naar hard, op wat je het minst hebt gehoord, of op titel. Zoeken geeft meerdere versies zodat je zelf de juiste kiest,
geen radio edit of instrumental waar je het origineel wilde. Achter elk nummer staat
zijn energie van 1 tot 5, die je daar kunt bijstellen, en een knop Nu om het meteen
op te zetten zonder de rest van de wachtrij kwijt te raken. Nieuwe nummers beginnen op 3,
en zolang ze daar staan doet de energiefader weinig met ze.

**Smaak** toont alles wat je hebt beoordeeld, met de mogelijkheid het terug te
draaien. Daaronder staat wat je net hebt gehoord, en welke nummers uit je set nog
nooit zijn langsgekomen; die kun je daar meteen opzetten. Achter elk nummer in de
Setlist-tab staat hoe vaak je het hebt gehoord.

**Show** is volledig scherm tijdens het luisteren, met de knop op de spelertab. In
Setup kies je wat je ziet: niks, een draaiende plaat met de hoes als label, of een
club met een dj achter de booth, zwaaiende lichtbundels en publiek met de handen in
de lucht. Je albumhoes staat dan op de wand achter de dj.

Het reageert niet op de muziek zelf: die audio gaat rechtstreeks van Apple Music naar
je speaker en is niet te analyseren. Wat het wel volgt zijn de kleuren van de hoes,
de voortgang van het nummer en de drops die je hebt gemarkeerd; tijdens een drop gaan
de lichten wit en beweegt alles sneller.

**Setup** kiest je speaker en je catalogus, test de verbinding, beheert de drops en
zet er een slot op.

## Slot

Standaard zit er geen slot op: iedereen op je wifi die het adres kent kan je muziek
bedienen. Thuis is dat meestal prima. Stel in de Setup-tab een code in en elk ander
apparaat moet die eerst invullen; je blijft daarna een maand ingelogd. Leeg laten
haalt het slot er weer af.

Wees eerlijk over wat dit is: het verkeer loopt onversleuteld over je eigen netwerk.
Het houdt huisgenoten en gasten buiten, het is geen beveiliging tegen iemand die
kwaad wil op hetzelfde netwerk.

## Hoe de keuze tot stand komt

De kans van een nummer is jouw oordeel keer de mood-match.

- **jouw oordeel**: een hart verdubbelt het gewicht tot maximaal acht keer, een kruis
  zet het op nul en dan komt hij nooit meer langs
- **de mood**: hoe goed genre en energie passen bij je schuiven

Die twee vermenigvuldigen. Een geliket nummer dat niet bij je mood past komt dus nog
steeds weinig langs, en dat is de bedoeling.

Energie staat los van het volume waarop je een nummer draait. Zonder eigen waarde
wordt hij uit het setvolume afgeleid, maar dat klopt lang niet altijd: de hiphop
stond als warm-up laag in de set en kreeg daardoor overal energie 1 of 2, waardoor
hij bij elke normale stand van de energiefader wegviel. Zet de energie per nummer in
de Setlist-tab op hoe druk het klinkt, niet op hoe hard je het draait.

De stijlfader deelt door het aantal nummers van elke soort. Anders wint de grootste
groep altijd, en bepaalt de toevallige samenstelling van je set de verhouding in
plaats van de fader. Genre komt van Apple Music.

Een track herhaalt niet binnen twaalf nummers. Daardoor haalt een favoriet niet
precies zijn volle gewicht: met 54 tracks komt een geliket nummer ongeveer anderhalf
keer zo vaak langs, na twee likes ruim twee keer.

## Drops

Staat standaard uit. In Setup zet je hem aan, en dan verschijnt op de spelertab de
knop Drop nu. Bij een gemarkeerd moment gaat het volume zes punten omhoog, ruim een
halve minuut lang, en daarna terug. Staat hij uit, dan blijft het volume waar jij het
zet en is de knop weg.

Waar die drop zit weet het programma niet: Apple Music levert DRM-beschermde audio
rechtstreeks aan de speaker, er is geen signaal om te analyseren. Spotify had een
API die de secties van een nummer teruggaf, maar die is sinds 27 november 2024 dicht
voor nieuwe apps, en de alternatieven geven alleen cijfers over het hele nummer zoals
BPM en energie.

Dus: druk tijdens een nummer op **Drop nu** en dat moment wordt onthouden. In Setup
kun je overal een schatting laten zetten op basis van de tracklengte, rond een vijfde
bij house en later bij hiphop. Die staat als geschat gemarkeerd en verdwijnt zodra je
zelf markeert.

## Vanaf de terminal

```
dj ui            de webinterface (dit wil je meestal)
dj speakers      welke speakers zie ik
dj check         de setlist nalopen zonder af te spelen
dj live          de set op volgorde, zonder interface
dj next          volgende
dj vol 30        volume
dj stop          stoppen en wachtrij legen
```

## setlist.json

- `speaker` / `speaker_ip` - de naam van je box, precies zoals in de Sonos-app. Het
  IP vul je alleen als het zoeken op het netwerk faalt.
- `volume` - startvolume.
- `crossfade` - de korte overlap die Sonos zelf kan.
- `country` - landcode voor de Apple Music-catalogus.
- `drops_aan` - of het volume omhoog gaat bij een gemarkeerde drop. Zet je in Setup.
- `tracks[]` - `{ "q": "artiest titel", "volume": 26, "energie": 4, "cut": 25 }`. Met
  `cut` sla je de laatste seconden over, met een volumedip over de knip heen. Met
  `energie` overschrijf je wat er uit het volume wordt afgeleid. In plaats van `q`
  mag ook `url` met een directe Apple Music-link. De Setlist-tab schrijft die vorm
  zelf.

## Wat niet kan

Echt mixen. Apple Music levert DRM-beschermde audio en een Sonos speelt maar een
stream tegelijk, dus twee decks bestaan niet. Geen beatmatching, geen overgangen op
de maat. Wat je krijgt is selectie, volgorde, energieopbouw, volume-automatisering en
die cut.

Sommige Nederlandse hiphop staat niet in de zoekindex, want die dekt de iTunes Store
en niet de hele streamingcatalogus. SFB is daar een voorbeeld van: alleen
instrumentals. Vind je zo'n nummer wel in de Apple Music-app, kopieer dan de
share-link en zet hem als `url` in de setlist.

## Het draait op je eigen machine

De besturing van een Sonos gaat over je lokale netwerk, dus er moet iets op dat
netwerk draaien. Een server in de cloud kan niet bij je speaker. Zolang de muziek
speelt wordt de slaapstand tegengehouden, zodat een set niet halverwege stilvalt;
je scherm mag gewoon uit. Wil je niet elke keer zelf starten:

```
dj autostart aan
dj autostart uit
```

Dat zet een klein opstartbestand in je Startup-map, meer niet.

## Onderhoud tijdens het draaien

De wachtrij wordt opgeruimd zodra er meer dan veertig afgespeelde nummers in staan,
anders wordt elke toevoeging langzamer. Valt de speaker weg, bijvoorbeeld omdat hij
uit gaat of even van de wifi valt, dan wordt na drie mislukte pogingen opnieuw
verbonden in plaats van dezelfde fout te blijven herhalen.

## Privé

`setlist.json`, `smaak.json`, `drops.json`, `geschiedenis.json` en `spotify.json`
staan in `.gitignore`. Dat is jouw muziek
en jouw oordeel, dat hoort niet in een repo. Wie dit binnenhaalt begint met de
voorbeeldset en bouwt zijn eigen lijst op.
