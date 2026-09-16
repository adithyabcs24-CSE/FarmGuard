import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.database import engine, SessionLocal, Base
from backend.models import User, Crop, Scan, Disease
from backend.auth import hash_password
from backend.ai_engine import AGRONOMY_KNOWLEDGE_BASE


def seed_database():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Seed create_all note: {e}")

    try:
        db: Session = SessionLocal()
    except Exception as e:
        print(f"SessionLocal error during seed: {e}")
        return

    try:
        # Check if already seeded
        if db.query(User).filter(User.email == "alice@farmguard.ai").first():
            print("Database already seeded with demo data.")
            return

        print("Seeding FarmGuard AI database with demo data...")

        # 1. Seed Demo Farmers
        pwd_hash = hash_password("password123")
        alice = User(
            name="Alice Sharma",
            email="alice@farmguard.ai",
            phone="+91 98765 43210",
            location="Nashik, Maharashtra",
            preferred_language="English",
            primary_crop="Tomato",
            plan_tier="Active",
            scans_used_this_month=2,
            password_hash=pwd_hash,
            created_at=datetime.utcnow() - timedelta(days=30)
        )
        db.add(alice)

        rajesh = User(
            name="Rajesh Patel",
            email="rajesh@farmguard.ai",
            phone="+91 91234 56789",
            location="Surat, Gujarat",
            preferred_language="English",
            primary_crop="Cotton",
            plan_tier="Active",
            scans_used_this_month=1,
            password_hash=pwd_hash,
            created_at=datetime.utcnow() - timedelta(days=45)
        )
        db.add(rajesh)
        db.commit()
        db.refresh(alice)
        db.refresh(rajesh)

        # 2. Seed Crops for Alice
        crop_tomato = Crop(
            user_id=alice.id,
            name="Tomato",
            variety="Roma Hybrid",
            area_acres=2.0,
            planting_date="15 July 2026",
            location="North Field - Block A",
            health_status="Attention Required",
            notes="Drip irrigated. Showing concentric brown leaf spots on lower foliage.",
            created_at=datetime.utcnow() - timedelta(days=28)
        )
        crop_potato = Crop(
            user_id=alice.id,
            name="Potato",
            variety="Kufri Jyoti",
            area_acres=1.5,
            planting_date="01 August 2026",
            location="South Terrace",
            health_status="Monitoring",
            notes="Recent humid spell; preventative biological spray planned.",
            created_at=datetime.utcnow() - timedelta(days=20)
        )
        crop_chili = Crop(
            user_id=alice.id,
            name="Chili",
            variety="Guntur Sanam",
            area_acres=0.8,
            planting_date="10 August 2026",
            location="East Plot",
            health_status="Healthy",
            notes="Uniform dark green vegetative growth, flower bud initiation.",
            created_at=datetime.utcnow() - timedelta(days=12)
        )
        db.add_all([crop_tomato, crop_potato, crop_chili])

        # Seed Crops for Rajesh
        crop_cotton = Crop(
            user_id=rajesh.id,
            name="Cotton",
            variety="Bt Hybrid RCH-2",
            area_acres=3.5,
            planting_date="20 June 2026",
            location="Main Canal Field",
            health_status="Attention Required",
            notes="Square formation stage. Whitefly pressure observed on lower leaves.",
            created_at=datetime.utcnow() - timedelta(days=40)
        )
        crop_maize = Crop(
            user_id=rajesh.id,
            name="Maize",
            variety="Pioneer Sweet Corn",
            area_acres=2.0,
            planting_date="05 July 2026",
            location="West Plot",
            health_status="Monitoring",
            notes="Mid-whorl stage. Installed pheromone traps.",
            created_at=datetime.utcnow() - timedelta(days=35)
        )
        db.add_all([crop_cotton, crop_maize])
        db.commit()
        db.refresh(crop_tomato)
        db.refresh(crop_potato)
        db.refresh(crop_chili)
        db.refresh(crop_cotton)

        # 3. Seed Scans
        scan1 = Scan(
            user_id=alice.id,
            crop_id=crop_tomato.id,
            crop_name="Tomato",
            image_url="/assets/hero-crop.jpg",
            problem_name="Early Blight",
            scientific_name="Alternaria solani",
            problem_type="Fungal",
            severity="High",
            confidence_pct=89,
            symptoms_json=json.dumps([
                "Concentric dark-brown rings forming a 'target board' pattern on older leaves",
                "Progressive yellowing (chlorosis) around dark necrotic lesions",
                "Premature leaf drop starting from lower canopy moving upward"
            ]),
            immediate_actions_json=json.dumps([
                "Immediately prune and safely destroy infected lower leaves (do not compost)",
                "Switch to drip irrigation or water strictly at the soil base in early morning",
                "Increase plant spacing to enhance airflow"
            ]),
            organic_remedies_json=json.dumps([
                "Neem Oil Spray (10,000 ppm) at 5 ml/liter water with mild surfactant every 7 days",
                "Foliar application of Trichoderma viride @ 5g/liter",
                "Fermented sour buttermilk foliar spray (1:10 dilution)"
            ]),
            chemical_controls_json=json.dumps([
                "Mancozeb 75% WP @ 2.0 to 2.5 g/L of water (Pre-harvest interval: 7 days)",
                "Chlorothalonil 75% WP @ 2.0 g/L or Azoxystrobin 23% SC @ 1 ml/L"
            ]),
            prevention_tips_json=json.dumps([
                "Rotate crops for at least 2-3 seasons away from solanaceous crops",
                "Apply organic straw mulch around plant base to prevent soil spore splash"
            ]),
            status="Monitoring",
            notes_json=json.dumps([
                f"{(datetime.utcnow() - timedelta(days=4)).strftime('%d %b %Y, %I:%M %p')} — Initial AI scan completed: Early Blight (89% confidence).",
                f"{(datetime.utcnow() - timedelta(days=2)).strftime('%d %b %Y, %I:%M %p')} — Pruned bottom 4 leaves and sprayed neem oil emulsion."
            ]),
            created_at=datetime.utcnow() - timedelta(days=4)
        )

        scan2 = Scan(
            user_id=alice.id,
            crop_id=crop_potato.id,
            crop_name="Potato",
            image_url="/assets/hero-crop.jpg",
            problem_name="Early Blight",
            scientific_name="Alternaria solani",
            problem_type="Fungal",
            severity="Medium",
            confidence_pct=85,
            symptoms_json=json.dumps([
                "Dark brown circular spots with concentric rings on older leaves",
                "Leaf margin senescing and slight chlorosis"
            ]),
            immediate_actions_json=json.dumps([
                "Apply balanced potassium fertilizer to improve foliar disease resistance",
                "Remove heavily blighted leaves"
            ]),
            organic_remedies_json=json.dumps([
                "Neem seed kernel extract (NSKE 5%) foliar spray",
                "Trichoderma viride foliar treatment @ 5 g/liter"
            ]),
            chemical_controls_json=json.dumps([
                "Mancozeb 75% WP @ 2.5 g/L",
                "Difenoconazole 25% EC @ 0.5 ml/L"
            ]),
            prevention_tips_json=json.dumps([
                "Avoid overhead irrigation; water along furrows",
                "3-year crop rotation with legumes"
            ]),
            status="Monitoring",
            notes_json=json.dumps([
                f"{(datetime.utcnow() - timedelta(days=2)).strftime('%d %b %Y, %I:%M %p')} — Routine inspection scan recorded."
            ]),
            created_at=datetime.utcnow() - timedelta(days=2)
        )

        db.add_all([scan1, scan2])

        # 4. Seed Disease Encyclopedia
        for crop_name, disease_list in AGRONOMY_KNOWLEDGE_BASE.items():
            for item in disease_list:
                d = Disease(
                    crop=crop_name,
                    name=item["problem_name"],
                    scientific_name=item.get("scientific_name", ""),
                    category=item.get("problem_type", "Fungal"),
                    severity_level=item.get("severity", "Medium"),
                    description=item.get("summary", ""),
                    symptoms_json=json.dumps(item.get("symptoms", [])),
                    organic_controls_json=json.dumps(item.get("organic_remedies", [])),
                    chemical_controls_json=json.dumps(item.get("chemical_controls", [])),
                    prevention_json=json.dumps(item.get("prevention_tips", [])),
                    image_url="/assets/hero-crop.jpg"
                )
                db.add(d)

        db.commit()
        print("FarmGuard AI database seeding completed successfully.")

    except Exception as e:
        db.rollback()
        print("Error seeding database:", e)
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
