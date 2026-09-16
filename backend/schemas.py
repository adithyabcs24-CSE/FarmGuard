from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# --- Auth & User ---
class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    phone: Optional[str] = ""
    location: Optional[str] = ""
    preferred_language: Optional[str] = "English"
    primary_crop: Optional[str] = "Tomato"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    preferred_language: Optional[str] = None
    primary_crop: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str
    location: str
    preferred_language: str
    primary_crop: str
    plan_tier: str
    scans_used_this_month: int
    scan_limit: int
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --- Crops ---
class CropCreate(BaseModel):
    name: str
    variety: Optional[str] = ""
    area_acres: Optional[float] = 1.0
    planting_date: Optional[str] = ""
    location: Optional[str] = ""
    health_status: Optional[str] = "Healthy"
    notes: Optional[str] = ""


class CropUpdate(BaseModel):
    name: Optional[str] = None
    variety: Optional[str] = None
    area_acres: Optional[float] = None
    planting_date: Optional[str] = None
    location: Optional[str] = None
    health_status: Optional[str] = None
    notes: Optional[str] = None


class CropOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    variety: str
    area_acres: float
    planting_date: str
    location: str
    health_status: str
    notes: str
    created_at: datetime
    recent_scans_count: int = 0


# --- Diagnosis & Scans ---
class ScanAnalyzeRequest(BaseModel):
    crop_name: str = "Tomato"
    plant_part: str = "Leaf"
    observations: str = ""
    language: str = "English"
    crop_id: Optional[int] = None
    image_base64: Optional[str] = None
    sample_image_url: Optional[str] = None


class DiagnosisResult(BaseModel):
    crop_name: str
    problem_name: str
    scientific_name: str
    problem_type: str
    severity: str
    confidence_pct: int
    symptoms: List[str]
    immediate_actions: List[str]
    organic_remedies: List[str]
    chemical_controls: List[str]
    prevention_tips: List[str]
    advisory_summary: str
    advisory_audio_text: str


class ScanStatusUpdate(BaseModel):
    status: str  # Monitoring, Improving, Resolved


class ScanNoteCreate(BaseModel):
    note: str


class ScanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    crop_id: Optional[int]
    crop_name: str
    image_url: str
    problem_name: str
    scientific_name: str
    problem_type: str
    severity: str
    confidence_pct: int
    symptoms: List[str]
    immediate_actions: List[str]
    organic_remedies: List[str]
    chemical_controls: List[str]
    prevention_tips: List[str]
    status: str
    notes: List[str]
    created_at: datetime


# --- Diseases ---
class DiseaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    crop: str
    name: str
    scientific_name: str
    category: str
    severity_level: str
    description: str
    symptoms: List[str]
    organic_controls: List[str]
    chemical_controls: List[str]
    prevention: List[str]
    image_url: str


# --- Advisory & Weather ---
class WeatherAdvisory(BaseModel):
    location: str
    temperature_c: float
    humidity_pct: int
    condition: str
    disease_risk_level: str
    risk_alert: str
    recommended_actions: List[str]


class UpgradeRequest(BaseModel):
    plan_tier: str  # Free, Active, FPO


# --- Contact ---
class ContactCreate(BaseModel):
    name: str
    email: EmailStr
    subject: Optional[str] = "FarmGuard Support Request"
    category: Optional[str] = "General Inquiry"
    message: str


class ContactOut(BaseModel):
    id: int
    status: str = "received"
    message: str


# --- Voice AI Assistant ---
class VoiceAssistantMessage(BaseModel):
    role: str  # user, assistant
    content: str


class VoiceAssistantRequest(BaseModel):
    message: str
    language: str = "Hindi"  # Hindi, Marathi, English
    crop_context: Optional[str] = None
    history: Optional[List[VoiceAssistantMessage]] = None


class VoiceAssistantResponse(BaseModel):
    reply: str
    audio_text: str
    language: str
    detected_crop: Optional[str] = None
    detected_problem: Optional[str] = None
    suggested_actions: List[str] = []
    follow_ups: List[str] = []


class QuickPromptItem(BaseModel):
    category: str
    crop: str
    prompt: str
    language: str


# ── Stub schemas for provider/booking/admin/notification routers ──────────────

class _AnyBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"

class MessageResponse(BaseModel):
    message: str

# --- Service Categories ---
class ServiceCategoryResponse(_AnyBase):
    id: int
    name: str
    description: str = ""
    is_active: str = "true"

class CategoryCreateRequest(BaseModel):
    name: str
    description: str = ""

class CategoryUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class CategoryDetailResponse(_AnyBase):
    id: int
    name: str
    description: str = ""

# --- Provider ---
class ProviderProfileUpdateRequest(BaseModel):
    bio: Optional[str] = None
    experience_years: Optional[int] = None
    location: Optional[str] = None

class ProviderProfileResponse(_AnyBase):
    id: int
    user_id: int
    bio: str = ""
    experience_years: int = 0
    is_verified: str = "false"
    rating: float = 0.0

class ProviderDetailResponse(ProviderProfileResponse):
    pass

class ProviderServiceCreateRequest(BaseModel):
    name: str
    description: str = ""
    price_per_acre: float = 0.0

class ProviderServiceResponse(_AnyBase):
    id: int
    name: str
    price_per_acre: float = 0.0

class ProviderVerificationSubmitRequest(BaseModel):
    document_url: Optional[str] = None
    notes: Optional[str] = None

class ProviderVerificationActionRequest(BaseModel):
    action: str  # approve / reject
    reason: Optional[str] = None

class ProviderLocationUpdateRequest(BaseModel):
    latitude: float
    longitude: float
    location: Optional[str] = None

class ProviderSearchItemResponse(BaseModel):
    id: int
    name: Optional[str] = None
    rating: float = 0.0

class ProviderScoreBreakdown(BaseModel):
    provider_id: int
    score: float = 0.0

class ProviderReRankResponse(BaseModel):
    providers: List[ProviderScoreBreakdown] = []

class RankedProviderItemResponse(BaseModel):
    id: int
    name: Optional[str] = None
    score: float = 0.0

class PriceEstimateRequest(BaseModel):
    service_id: int
    area_acres: float

class PriceEstimateResponse(BaseModel):
    total: float
    breakdown: str = ""

class AvailabilitySlotCreateRequest(BaseModel):
    day_of_week: str
    start_time: str = "09:00"
    end_time: str = "17:00"
    is_available: str = "true"

class AvailabilitySlotResponse(_AnyBase):
    id: int
    day_of_week: str
    start_time: str
    end_time: str
    is_available: str

# --- Bookings ---
class BookingCreateRequest(BaseModel):
    provider_id: int
    service_id: Optional[int] = None
    scheduled_date: str
    scheduled_time: str = ""
    area_acres: float = 1.0
    crop_type: str = ""
    special_instructions: str = ""

class EmergencyBookingCreateRequest(BaseModel):
    provider_id: int
    service_id: Optional[int] = None
    area_acres: float = 1.0
    crop_type: str = ""
    reason: str = ""

class QuoteRequestCreate(BaseModel):
    provider_id: int
    service_id: Optional[int] = None
    area_acres: float = 1.0
    crop_type: str = ""
    message: str = ""

class QuoteAcceptResponse(BaseModel):
    booking_id: int
    status: str = "Pending"

class BookingStatusUpdateRequest(BaseModel):
    status: str
    reason: Optional[str] = None

class BookingTrackingResponse(BaseModel):
    booking_id: int
    status: str
    updates: List[str] = []

class BookingResponse(_AnyBase):
    id: int
    booking_ref: Optional[str] = None
    status: str = "Pending"
    scheduled_date: str = ""
    total_amount: float = 0.0

class BookingDetailResponse(BookingResponse):
    area_acres: float = 1.0
    crop_type: str = ""

# --- Complaints ---
class ComplaintCreateRequest(BaseModel):
    booking_id: int
    title: str
    description: str = ""

class ComplaintResponse(_AnyBase):
    id: int
    booking_id: int
    title: str
    status: str = "Open"

# --- Reviews ---
class ReviewCreateRequest(BaseModel):
    booking_id: int
    rating: int = 5
    comment: str = ""

class ReviewResponse(_AnyBase):
    id: int
    booking_id: int
    rating: int
    comment: str = ""

# --- Payments & Invoices ---
class PaymentResponse(_AnyBase):
    id: int
    booking_id: int
    amount: float
    status: str = "Pending"

class InvoiceResponse(_AnyBase):
    id: int
    booking_id: int
    invoice_number: str = ""
    amount: float = 0.0
    status: str = "Draft"

# --- Additional Charges ---
class AdditionalChargeCreateRequest(BaseModel):
    label: str
    amount: float

class AdditionalChargeActionRequest(BaseModel):
    action: str  # accept / reject

class AdditionalChargeResponse(_AnyBase):
    id: int
    booking_id: int
    label: str
    amount: float
    status: str = "Pending"

# --- Address ---
class AddressCreateRequest(BaseModel):
    label: str = "Home"
    line1: str = ""
    city: str = ""
    state: str = ""
    pincode: str = ""
    latitude: float = 0.0
    longitude: float = 0.0

class AddressResponse(_AnyBase):
    id: int
    label: str
    line1: str = ""
    city: str = ""
    state: str = ""
    pincode: str = ""

# --- Chat ---
class ChatMessageCreateRequest(BaseModel):
    message: str

class ChatMessageResponse(_AnyBase):
    id: int
    booking_id: int
    message: str
    created_at: datetime

# --- Notifications ---
class NotificationResponse(_AnyBase):
    id: int
    user_id: int
    message: str
    is_read: str = "false"
    created_at: datetime

class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse] = []
    unread_count: int = 0

class NotificationMarkReadRequest(BaseModel):
    notification_ids: List[int] = []

# --- Admin ---
class AdminUserResponse(_AnyBase):
    id: int
    name: str
    email: str
    plan_tier: str = "Free"

class UserBlockUpdateRequest(BaseModel):
    blocked: bool

class AdminBookingForceCancelRequest(BaseModel):
    booking_id: int
    reason: str = ""

class AdminComplaintActionRequest(BaseModel):
    complaint_id: int
    action: str
    resolution: str = ""

class AdminAnalyticsResponse(BaseModel):
    total_users: int = 0
    total_bookings: int = 0
    total_revenue: float = 0.0

# --- AI Diagnosis ---
class ServiceClassifyRequest(BaseModel):
    description: str

class ServiceClassifyResponse(BaseModel):
    category: str
    confidence: float = 1.0

class ProblemDiagnoseRequest(BaseModel):
    description: str
    crop_type: str = ""

class FollowUpQuestion(BaseModel):
    question: str

class ProblemDiagnoseResponse(BaseModel):
    diagnosis: str
    confidence: float = 1.0
    follow_ups: List[FollowUpQuestion] = []


