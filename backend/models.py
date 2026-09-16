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


# ── Extended models used by provider/booking/admin routers ─────────────────────

class ServiceCategory(Base):
    __tablename__ = "service_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True)
    description = Column(Text, default="")
    is_active = Column(String(10), default="true")
    created_at = Column(DateTime, default=datetime.utcnow)


class ProviderProfile(Base):
    __tablename__ = "provider_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    bio = Column(Text, default="")
    experience_years = Column(Integer, default=0)
    is_verified = Column(String(10), default="false")
    is_available = Column(String(10), default="true")
    rating = Column(Float, default=0.0)
    total_reviews = Column(Integer, default=0)
    total_bookings = Column(Integer, default=0)
    location = Column(String(200), default="")
    latitude = Column(Float, default=0.0)
    longitude = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    services = relationship("ProviderService", back_populates="provider", cascade="all, delete-orphan")


class ProviderService(Base):
    __tablename__ = "provider_services"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("provider_profiles.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("service_categories.id"), nullable=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, default="")
    price_per_acre = Column(Float, default=0.0)
    min_acres = Column(Float, default=1.0)
    max_acres = Column(Float, default=100.0)
    is_active = Column(String(10), default="true")
    created_at = Column(DateTime, default=datetime.utcnow)

    provider = relationship("ProviderProfile", back_populates="services")
    category = relationship("ServiceCategory")


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("provider_profiles.id"), nullable=False, index=True)
    day_of_week = Column(String(20), nullable=False)  # Monday, Tuesday...
    start_time = Column(String(10), default="09:00")
    end_time = Column(String(10), default="17:00")
    is_available = Column(String(10), default="true")

    provider = relationship("ProviderProfile")


class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    label = Column(String(80), default="Home")
    line1 = Column(String(200), default="")
    line2 = Column(String(200), default="")
    city = Column(String(100), default="")
    state = Column(String(100), default="")
    pincode = Column(String(20), default="")
    latitude = Column(Float, default=0.0)
    longitude = Column(Float, default=0.0)
    is_default = Column(String(10), default="false")

    user = relationship("User")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    booking_ref = Column(String(50), unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("provider_profiles.id"), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("provider_services.id"), nullable=True)
    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=True)
    status = Column(String(50), default="Pending")
    scheduled_date = Column(String(50), default="")
    scheduled_time = Column(String(20), default="")
    area_acres = Column(Float, default=1.0)
    crop_type = Column(String(100), default="")
    special_instructions = Column(Text, default="")
    total_amount = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("User", foreign_keys=[customer_id])
    provider = relationship("ProviderProfile", foreign_keys=[provider_id])
    service = relationship("ProviderService", foreign_keys=[service_id])
    address = relationship("Address", foreign_keys=[address_id])


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    amount = Column(Float, default=0.0)
    status = Column(String(50), default="Pending")
    method = Column(String(50), default="Cash")
    transaction_id = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("Booking")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    invoice_number = Column(String(100), unique=True, index=True)
    amount = Column(Float, default=0.0)
    status = Column(String(50), default="Draft")
    issued_at = Column(DateTime, default=datetime.utcnow)
    due_date = Column(String(50), default="")
    notes = Column(Text, default="")

    booking = relationship("Booking")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("provider_profiles.id"), nullable=False, index=True)
    rating = Column(Integer, default=5)
    comment = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("Booking")
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    provider = relationship("ProviderProfile", foreign_keys=[provider_id])


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    filed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    status = Column(String(50), default="Open")  # Open, Investigating, Resolved, Dismissed
    resolution = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    booking = relationship("Booking")
    filed_by = relationship("User", foreign_keys=[filed_by_id])


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("Booking")
    sender = relationship("User", foreign_keys=[sender_id])


class AdditionalCharge(Base):
    __tablename__ = "additional_charges"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    label = Column(String(200), nullable=False)
    amount = Column(Float, default=0.0)
    status = Column(String(50), default="Pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("Booking")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    is_read = Column(String(10), default="false")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")

