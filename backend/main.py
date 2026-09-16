import sys
from pathlib import Path

# Ensure project root is in sys.path for serverless runtimes (like Vercel)
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from backend.database import engine, Base
import backend.models  # Register all models with Base
from backend.routers import auth, crops, scans, diseases, advisory, contact, assistant
from backend.config import STATIC_DIR, UPLOAD_DIR

from contextlib import asynccontextmanager

# Create database tables
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Database initialization warning: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from backend.seed import seed_database
        seed_database()
    except Exception as e:
        print(f"Startup seeding warning: {e}")
    yield

app = FastAPI(
    title="FarmGuard AI API",
    version="1.0.0",
    description="Early Crop Problem & Pest Detection Platform API",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include domain routers
app.include_router(auth.router)
app.include_router(crops.router)
app.include_router(scans.router)
app.include_router(diseases.router)
app.include_router(advisory.router)
app.include_router(contact.router)
app.include_router(assistant.router)


@app.get("/api/health", tags=["health"])
def health_check():
    return {
        "status": "healthy",
        "service": "FarmGuard AI",
        "version": "1.0.0"
    }


# Ensure static subdirectories exist
try:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# Explicit route handlers for clean URLs
@app.get("/", include_in_schema=False)
def get_home_page():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return RedirectResponse(url="/index.html")


@app.get("/favicon.ico", include_in_schema=False)
def get_favicon():
    fav = STATIC_DIR / "favicon.ico"
    if fav.exists():
        return FileResponse(fav)
    from fastapi.responses import Response
    return Response(status_code=204)


@app.get("/dashboard")
def get_dashboard_page():
    dashboard_file = STATIC_DIR / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(dashboard_file)
    return RedirectResponse(url="/dashboard.html")


@app.get("/auth")
def get_auth_page():
    auth_file = STATIC_DIR / "auth.html"
    if auth_file.exists():
        return FileResponse(auth_file)
    return RedirectResponse(url="/auth.html")


@app.get("/about")
def get_about_page():
    f = STATIC_DIR / "about.html"
    if f.exists():
        return FileResponse(f)
    return RedirectResponse(url="/about.html")


@app.get("/contact")
def get_contact_page():
    f = STATIC_DIR / "contact.html"
    if f.exists():
        return FileResponse(f)
    return RedirectResponse(url="/contact.html")


@app.get("/privacy")
def get_privacy_page():
    f = STATIC_DIR / "privacy.html"
    if f.exists():
        return FileResponse(f)
    return RedirectResponse(url="/privacy.html")


@app.get("/terms")
def get_terms_page():
    f = STATIC_DIR / "terms.html"
    if f.exists():
        return FileResponse(f)
    return RedirectResponse(url="/terms.html")


# Mount static assets
if UPLOAD_DIR.exists() and UPLOAD_DIR != (STATIC_DIR / "uploads"):
    app.mount("/static/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="static_uploads")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static_assets")
app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

# Mount root directory for static serving
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static_root")
