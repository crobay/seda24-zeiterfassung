from app.db.database import SessionLocal
from app.models.models import Customer, Object
from sqlalchemy import text
db = SessionLocal()

# Erst ALLES aufräumen (auch Zeiteinträge!)
print("=== AUFRÄUMEN ===")
db.execute(text("DELETE FROM time_entries"))  # <-- NEU: Erst Zeiteinträge
db.execute(text("DELETE FROM schedules"))     # <-- NEU: Auch Dienstpläne
db.execute(text("DELETE FROM objects"))       # <-- Dann Objekte
db.execute(text("DELETE FROM customers WHERE name != 'SEDA24 GmbH'"))
db.commit()
print("✅ Alle alten Einträge gelöscht")

# Dann der Rest bleibt gleich...
# Alle deine Kunden aus der Excel
KUNDEN_OBJEKTE = [
    {
        "kuerzel": "K1",
        "kunde": "Lidl Bietigheim",
        "objekt": "Lidl Muggensturmer Str",
        "adresse": "Muggensturmer Straße 2, 76467 Bietigheim",
        "lat": 48.88882147744413,
        "lng": 8.264812506825914,
        "beginn": "15:00",
        "ende": "20:00",
        "stunden": 5,
        "tage": "werktags Mo-Fr"
    },
    {
        "kuerzel": "K2",
        "kunde": "Lidl Bietigheim",
        "objekt": "Lidl Wochenende",
        "adresse": "Muggensturmer Straße 2, 76467 Bietigheim",
        "lat": 48.88882147744413,
        "lng": 8.264812506825914,
        "beginn": "11:00",
        "ende": "13:00",
        "stunden": 2,
        "tage": "nur Samstag"
    },
    {
        "kuerzel": "K3",
        "kunde": "Enfido",
        "objekt": "Enfido Sonnenschein",
        "adresse": "Im Sonnenschein 3, 76467 Bietigheim",
        "lat": 48.90906468830345,
        "lng": 8.261018504823674,
        "beginn": "17:30",
        "ende": "20:00",
        "stunden": 2.5,
        "tage": "Mittwoch"
    },
    {
        "kuerzel": "K6",
        "kunde": "Metalicone",
        "objekt": "Metalicone Muggensturm",
        "adresse": "Henkelstr. 14, 76461 Muggensturm",
        "lat": 48.87971339350924,
        "lng": 8.280356364865641,
        "beginn": "18:00",
        "ende": "20:45",
        "stunden": 2.75,
        "tage": "Wochenende 1x"
    },
    {
        "kuerzel": "K9",
        "kunde": "JU_RA",
        "objekt": "JU_RA Baden-Baden",
        "adresse": "Markgrafenstr. 28, 76530 Baden-Baden",
        "lat": 48.761231974953006,
        "lng": 8.250515553471368,
        "beginn": "15:00",
        "ende": "18:00",
        "stunden": 3,
        "tage": "alle 14 Tage ab KW 34"
    },
    {
        "kuerzel": "K10",
        "kunde": "Huber",
        "objekt": "Huber Iffezheim",
        "adresse": "Südring 11, 76473 Iffezheim",
        "lat": 48.81671038905296,
        "lng": 8.15985572143728,
        "beginn": "17:15",
        "ende": "20:45",
        "stunden": 3.5,
        "tage": "Mi und Fr"
    },
    {
        "kuerzel": "K11",
        "kunde": "BAD-Treppen",
        "objekt": "BAD-Treppen",
        "adresse": "Hardäckerstr. 2, 76530 Baden-Baden",
        "lat": 48.757677138576106,
        "lng": 8.2450594664259,
        "beginn": "11:00",
        "ende": "12:30",
        "stunden": 1.5,
        "tage": "alle 14 Tage ab KW 34"
    },
    {
        "kuerzel": "K12",
        "kunde": "Seda GmbH",
        "objekt": "Seda Oberwald",
        "adresse": "Oberwaldstr. 11a, 76532 Baden-Baden",
        "lat": 48.80752977392799,
        "lng": 8.191089508584882,
        "beginn": "11:30",
        "ende": "17:30",
        "stunden": 6,
        "tage": "spontan ab und zu"
    },
    {
        "kuerzel": "K13",
        "kunde": "Leible GmbH",
        "objekt": "Leible Rheinmünster",
        "adresse": "Körnersbühnd 2, 77836 Rheinmünster",
        "lat": 48.749857204674726,
        "lng": 8.03728945082595,
        "beginn": "20:45",
        "ende": "23:45",
        "stunden": 3,
        "tage": "Mo und Do"
    },
    {
        "kuerzel": "K15",
        "kunde": "Zinsfabrik",
        "objekt": "Zinsfabrik Baden-Baden",
        "adresse": "Lange Str. 61, 76530 Baden-Baden",
        "lat": 48.7664297331758,
        "lng": 8.23475597645378,
        "beginn": "17:00",
        "ende": "19:30",
        "stunden": 2.5,
        "tage": "Samstag"
    },
    {
        "kuerzel": "K16",
        "kunde": "Polytec",
        "objekt": "Polytec Rastatt",
        "adresse": "Karlsruher Strasse 33, 76437 Rastatt",
        "lat": 48.865778155162666,
        "lng": 8.221102849763769,
        "beginn": "16:00",
        "ende": "19:00",
        "stunden": 3,
        "tage": "Samstag"
    },
    {
        "kuerzel": "K17",
        "kunde": "Steuerberater BB",
        "objekt": "Steuerberater Baden-Baden",
        "adresse": "Prinz-Weimar-Str. 12, 76530 Baden-Baden",
        "lat": 48.76115351265029,
        "lng": 8.24928112428465,
        "beginn": "9:00",
        "ende": "15:00",
        "stunden": 6,
        "tage": "Samstag"
    },
    {
        "kuerzel": "K18",
        "kunde": "Geiger GmbH",
        "objekt": "Geiger Malsch",
        "adresse": "Dieselstr. 9, 76316 Malsch",
        "lat": 48.889436183885365,
        "lng": 8.31018689424884,
        "beginn": "9:00",
        "ende": "13:30",
        "stunden": 4,
        "tage": "Samstag"
    },
    {
        "kuerzel": "K19",
        "kunde": "Rytec",
        "objekt": "Rytec Baden-Baden",
        "adresse": "Pariser Ring 37, 76532 Baden-Baden",
        "lat": 48.7783726814369,
        "lng": 8.202937572581309,
        "beginn": "11:00",
        "ende": "13:00",
        "stunden": 2,
        "tage": "Samstag"
    }
]

print("\n=== IMPORTIERE KUNDEN & OBJEKTE ===")
for item in KUNDEN_OBJEKTE:
    # Kunde anlegen/finden
    customer = db.query(Customer).filter(Customer.name == item["kunde"]).first()
    if not customer:
        customer = Customer(
            name=item["kunde"],
            billing_type="pauschale"
        )
        db.add(customer)
        db.flush()
        print(f"\n✅ Neuer Kunde: {item['kunde']}")
    
    # Objekt anlegen
    obj = Object(
        customer_id=customer.id,
        name=item["objekt"],
        address=item["adresse"],
        gps_lat=item["lat"],
        gps_lng=item["lng"],
        radius_m=100,  # 100m Radius für GPS
        reference_code=item["kuerzel"],
        cleaning_hours=f"{item['beginn']}-{item['ende']}",
        cleaning_days=item["tage"],
        planned_hours=item["stunden"]
    )
    db.add(obj)
    print(f"  → {item['kuerzel']}: {item['objekt']}")
    print(f"    Zeit: {item['beginn']}-{item['ende']} ({item['stunden']}h)")
    print(f"    Tage: {item['tage']}")

db.commit()

# Zusammenfassung
print("\n=== ZUSAMMENFASSUNG ===")
kunden = db.query(Customer).count()
objekte = db.query(Object).count()
print(f"✅ {kunden} Kunden angelegt")
print(f"✅ {objekte} Objekte angelegt")
print(f"\n🎉 Import erfolgreich!")
