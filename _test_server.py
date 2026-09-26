"""Tijdelijk: serveert de radiopagina met nepdata om de UI te bekijken."""
from http.server import ThreadingHTTPServer
import radio as R

fake = R.Radio.__new__(R.Radio)
fake.pool = [{"url": "u1", "label": "MK & CHRYSTAL - Dior", "art": ""}]
fake.smaak = {"u1": {"gewicht": 4.0, "label": "MK & CHRYSTAL - Dior"}}
fake.nu = lambda: {
    "titel": "Dior", "artiest": "MK, CHRYSTAL",
    "art": "https://is1-ssl.mzstatic.com/image/thumb/Music116/v4/2e/2b/dc/"
           "2e2bdc4e-7a3f-3d8f-4f0a-2a1f0d9c9a44/196871234567.jpg/600x600bb.jpg",
    "url": "u1", "label": "MK & CHRYSTAL - Dior", "gewicht": 4.0, "positie": 1,
}
ThreadingHTTPServer(("127.0.0.1", 8799), R.maak_handler(fake)).serve_forever()
