# Sonos DJ

Een DJ voor je Sonos die luistert naar wat jij van de muziek vindt. Jij zegt welke
kant het op moet, hij kiest de nummers, regelt het volume en onthoudt je oordeel.
Bedienen doe je in de browser, ook op je telefoon.

Python + [SoCo](https://github.com/SoCo/SoCo) voor de speaker, de iTunes Search API
voor de catalogus, en een pagina zonder frameworks of buildstap.

## Hoe het werkt

Elke track in `setlist.json` wordt opgezocht via de iTunes Search API en levert een
`music.apple.com`-link op. Die links gaan in de wachtrij van je speaker, die ze zelf
uit jouw Apple Music-abonnement streamt. De audio gaat nooit via je pc.

## Starten

```
cd sonos-dj
.\dj.bat ui
```

De terminal geeft twee adressen: een voor deze pc en een voor je telefoon. Open dat
laatste op je telefoon, zolang die op hetzelfde wifi zit.

Eerste keer: `python -m pip install soco requests`

## Inloggen

Nergens voor nodig. De speaker praat rechtstreeks met je pc over je eigen netwerk,
zonder account, wachtwoord of sleutel. Het enige dat eenmalig moet is Apple Music
koppelen in de Sonos-app zelf, bij Instellingen, Diensten en spraak. In de Setup-tab
zit een knop die vijf seconden een nummer opzet om te controleren of dat gelukt is.

De gekozen speaker wordt losgemaakt uit elke groep waar hij in zit, zodat alleen die
ene box speelt en niet je hele huis.

## De tabs

**Speler** toont wat er draait. De albumhoes is ook je swipe-kaart: naar rechts
vegen is vaker draaien, naar links is nooit meer. Op een breed scherm staat de hoes
links, de bediening in het midden en de wachtrij rechts.

**Mood** is waar je zegt wat je wilt horen. Drie schuiven: hiphop tegenover house,
rustig tegenover vol gas, en hoe strak hij bij dat niveau moet blijven. Verander je
de stand, dan worden de nummers die al klaarstonden weggegooid en opnieuw gekozen,
dus het werkt meteen en niet pas over vijf nummers.

**Nieuw** is de proefbak. Hij haalt nummers op van artiesten die bij je set passen,
je luistert het fragment van dertig seconden en bepaalt of hij in de rotatie komt.
Wat je afwijst wordt niet meer voorgesteld. Nummers die al in je set staan komen er
niet in, ook niet als dezelfde track op een ander album een andere link heeft.

**Setlist** is de pool. Zoeken geeft meerdere versies zodat je zelf de juiste kiest,
geen radio edit of instrumental waar je het origineel wilde.

**Smaak** toont alles wat je hebt beoordeeld, met de mogelijkheid het terug te
draaien.

**Setup** kiest je speaker, test de verbinding en beheert de drops.

## Hoe de keuze tot stand komt

De kans van een nummer is jouw oordeel keer de mood-match.

- **jouw oordeel**: een hart verdubbelt het gewicht tot maximaal acht keer, een kruis
  zet het op nul en dan komt hij nooit meer langs
- **de mood**: hoe goed genre en energie passen bij je schuiven

Die twee vermenigvuldigen. Een geliket nummer dat niet bij je mood past komt dus nog
steeds weinig langs, en dat is de bedoeling.

Energie per track komt uit het volume dat het in de set heeft gekregen: 17 is
achtergrond, 33 is vol gas, vertaald naar 1 tot 5. Genre komt van Apple Music.

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
- `tracks[]` - `{ "q": "artiest titel", "volume": 26, "cut": 25 }`. Met `cut` sla je
  de laatste seconden over, met een volumedip over de knip heen. In plaats van `q`
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

## Privé

`smaak.json` en `drops.json` staan in `.gitignore`. Dat zijn jouw oordelen, die horen
niet in een repo.
