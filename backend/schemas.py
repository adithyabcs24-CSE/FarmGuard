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

