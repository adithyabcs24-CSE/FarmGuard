import os
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import uvicorn
from backend.seed import seed_database
from backend.config import HOST, PORT, DEBUG

if __name__ == "__main__":
    seed_database()
    print("=" * 65)
    print(f"🌾 FarmGuard AI is running at: http://{HOST}:{PORT}")
    print(f"   - Landing Page:  http://{HOST}:{PORT}/")
    print(f"   - Auth / Login:  http://{HOST}:{PORT}/auth")
    print(f"   - Dashboard:     http://{HOST}:{PORT}/dashboard")
    print(f"   - API Docs:      http://{HOST}:{PORT}/docs")
    print("=" * 65)
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=DEBUG)

