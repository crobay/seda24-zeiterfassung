from app.db.database import SessionLocal
from app.models.models import Customer, Object

db = SessionLocal()

# Test-Kunde
customer = Customer(
    name="Sparkasse Gaggenau",
    address="Hauptstraße 45, 76571 Gaggenau",
    billing_type="pauschale",
    monthly_rate=2500.00
)
db.add(customer)
db.commit()

# Test-Objekt
obj = Object(
    customer_id=customer.id,
    name="Sparkasse Hauptfiliale",
    address="Hauptstraße 45, 76571 Gaggenau",
    gps_lat=48.8047,
    gps_lng=8.3339,
    radius_meters=100
)
db.add(obj)
db.commit()

print("✅ Test-Daten erstellt!")
print(f"Kunde: {customer.name} (ID: {customer.id})")
print(f"Objekt: {obj.name} (ID: {obj.id})")
