# FarmGuard AI — Early Crop Problem & Pest Detection Platform

FarmGuard AI is an agricultural technology platform designed to detect crop diseases and pest infestations early using image analysis, pathogen pattern recognition, and practical farmer guidance.

Inspired by [sprout-guard-now.lovable.app](https://sprout-guard-now.lovable.app), this application provides a complete, production-grade **FastAPI + SQLite backend** coupled with a responsive, accessible frontend interface.

---

## Features

- **📷 AI Crop Scanner & Diagnostic Engine**:
  - Image analysis with computer vision heuristics across 8+ major crops: **Tomato, Potato, Cotton, Rice, Wheat, Chili, Maize, and Onion**.
  - Identifies 25+ diseases, pests, nutrient deficiencies, and healthy states with diagnostic confidence percentages and severity classifications (*Healthy, Low, Medium, High, Critical*).
  - 1-Click quick test sample leaves provided in the dashboard for instant evaluation without needing physical field leaves.
- **🌱 Structured Agronomy Advisory**:
  - **Immediate Action Steps**: Urgent physical sanitation, pruning, and moisture control.
  - **Certified Organic & Biological Remedies**: Neem kernel extract, *Trichoderma viride*, *Pseudomonas fluorescens*, sour buttermilk, and bio-fungicides.
  - **Standard Chemical Controls**: Clear active ingredients with safe dilutions (e.g. Mancozeb 75% WP @ 2.5g/L, Azoxystrobin, Propiconazole) and pre-harvest intervals (PHI).
  - **Long-term Prevention & Cultural Practices**: Crop rotation, drip irrigation, mulch barriers, and certified seed selection.
- **🔊 Farmer Voice Narration (Text-to-Speech)**:
  - Built-in audio readout of diagnoses and action steps in **English, Hindi (हिंदी), or Marathi (मराठी)**.
- **🌾 Multi-Plot & Acreage Management**:
  - Add and manage field plots with crop varieties, planting dates, acreage, and real-time health badges (*Healthy, Monitoring, Attention Required*).
- **📋 Diagnostic Scan History & Field Log**:
  - Filterable diagnostic history with thumbnail previews, status tracker (*Monitoring → Improving → Resolved*), and timestamped field follow-up notes.
  - **🖨️ Printable PDF Field Advisory Reports**: One-click printable reports formatted for farmers, cooperatives, and extension agents.
- **📖 Searchable Crop Disease Encyclopedia**:
  - Browse over 25+ plant pathogens with scientific names, descriptions, visual symptoms, and organic bio-controls.
- **⛅ Agro-Climatic Weather Warning**:
  - Live temperature, relative humidity, and pathogen risk calculations (e.g. high morning humidity fungal risk).
- **⭐ Plan Tiers & Scan Quotas**:
  - **Free (₹0/mo)**: 5 scans/month
  - **Active Farm (₹199/mo)**: 50 scans/month
  - **FPO & Consultant (₹499/mo)**: 200 scans/month with priority tools.

---

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy ORM, SQLite database, Pydantic v2 validation.
- **Security**: JWT authentication (HS256) with bcrypt password hashing and Bearer tokens.
- **Frontend**: Responsive HTML5, modern CSS3 with Tailwind-aligned OKLCH color palettes, vanilla JavaScript, SpeechSynthesis API.
- **Assets**: Embedded hero imagery and vector iconography.

---

## Quick Start Guide

### 1. Environment Configuration
The project includes a pre-configured [.env](file:///Users/adithyab/Desktop/FarmGuard_AI/.env) file (and [.env.example](file:///Users/adithyab/Desktop/FarmGuard_AI/.env.example)). You can customize your host, port, secret key, or API credentials there:
```bash
cp .env.example .env
```

### 2. Launch the Server
```bash
.venv/bin/python run.py
```
Or with uvicorn:
```bash
PYTHONPATH=. .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser at [http://127.0.0.1:8000](http://127.0.0.1:8000) or navigate to:
- **Landing Page**: `http://127.0.0.1:8000/`
- **Login / Signup Screen**: `http://127.0.0.1:8000/auth`
- **Farmer Dashboard**: `http://127.0.0.1:8000/dashboard`
- **Interactive API Documentation (Swagger)**: `http://127.0.0.1:8000/docs`
- **About Page**: `http://127.0.0.1:8000/about`
- **Contact & Support Form**: `http://127.0.0.1:8000/contact`

### 2. Run Automated Test Suite
```bash
PYTHONPATH=. .venv/bin/pytest -v tests/test_farmguard.py
```

---

## Demo Accounts

Both demo accounts feature **1-click instant login buttons** directly on the `/auth` page.

| Farmer | Email | Password | Primary Crop | Location | Acreage & Plots |
|--------|-------|----------|--------------|----------|-----------------|
| **Alice Sharma** | `alice@farmguard.ai` | `password123` | Tomato | Nashik, Maharashtra | 4.3 Acres (Tomato, Potato, Chili) |
| **Rajesh Patel** | `rajesh@farmguard.ai` | `password123` | Cotton | Surat, Gujarat | 5.5 Acres (Cotton, Maize) |
