"""NUR DEV: kurzlebiges Zugriffstoken fuer einen Benutzer aus dev_cockpit erzeugen (fuer Screenshots/Pruefskripte),
ohne dessen Passwort zu kennen. Bricht ab, wenn die .env nicht auf dev_cockpit zeigt. Ausgabe nur auf stdout."""
import os, sys
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, B)
from dotenv import load_dotenv
load_dotenv(os.path.join(B, ".env"))
if not os.getenv("DATABASE_URL", "").endswith("/dev_cockpit"):
    sys.exit("Abbruch: nicht die DEV-Datenbank")
from app.core.security import create_access_token
print(create_access_token(data={"sub": sys.argv[1]}))
