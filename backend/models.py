from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    phone = Column(String(50), default="")
    location = Column(String(120), default="")
    preferred_language = Column(String(50), default="English")
    primary_crop = Column(String(100), default="Tomato")
    plan_tier = Column(String(50), default="Free")  # Free, Active, FPO
    scans_used_this_month = Column(Integer, default=0)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    crops = relationship("Crop", back_populates="user", cascade="all, delete-orphan")
    scans = relationship("Scan", back_populates="user", cascade="all, delete-orphan")


class Crop(Base):
    __tablename__ = "crops"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # Tomato, Cotton, Rice, etc.
    variety = Column(String(100), default="")
    area_acres = Column(Float, default=1.0)
    planting_date = Column(String(50), default="")
    location = Column(String(100), default="")
    health_status = Column(String(50), default="Healthy")  # Healthy, Monitoring, Attention Required
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="crops")
    scans = relationship("Scan", back_populates="crop")


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    crop_id = Column(Integer, ForeignKey("crops.id"), nullable=True)
    crop_name = Column(String(100), nullable=False)
    image_url = Column(String(500), default="/assets/hero-crop.jpg")
    problem_name = Column(String(150), nullable=False)
    scientific_name = Column(String(150), default="")
    problem_type = Column(String(50), default="Fungal")  # Fungal, Bacterial, Viral, Pest, Nutrient, Healthy
    severity = Column(String(50), default="Medium")  # Healthy, Low, Medium, High, Critical
    confidence_pct = Column(Integer, default=85)
    symptoms_json = Column(Text, default="[]")
    immediate_actions_json = Column(Text, default="[]")
    organic_remedies_json = Column(Text, default="[]")
    chemical_controls_json = Column(Text, default="[]")
    prevention_tips_json = Column(Text, default="[]")
    status = Column(String(50), default="Monitoring")  # Monitoring, Improving, Resolved
    notes_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="scans")
    crop = relationship("Crop", back_populates="scans")


class Disease(Base):
    __tablename__ = "diseases"

    id = Column(Integer, primary_key=True, index=True)
    crop = Column(String(100), nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    scientific_name = Column(String(150), default="")
    category = Column(String(50), default="Fungal")
    severity_level = Column(String(50), default="Medium")
    description = Column(Text, default="")
    symptoms_json = Column(Text, default="[]")
    organic_controls_json = Column(Text, default="[]")
    chemical_controls_json = Column(Text, default="[]")
    prevention_json = Column(Text, default="[]")
    image_url = Column(String(500), default="")


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(120), nullable=False)
    subject = Column(String(200), default="")
    category = Column(String(100), default="General Inquiry")
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
