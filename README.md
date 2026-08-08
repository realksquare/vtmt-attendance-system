# Smart Attendance System (FYP) 🎓📸

An advanced, privacy-first **Smart Attendance Tracking System** featuring **AES-256 GCM encrypted biometrics**, automated **Tri-Window Camera Burst Capture**, **2-out-of-3 Majority Voting Decision Engine**, **CLAHE Multi-Spectral Anti-Spoofing (PAD)**, **PWA Web Portal**, and dedicated **Staff Management & Biometric Directory**.

---

## ✨ Features

- **🔐 AES-256 GCM Biometric Privacy:** All 512-D InsightFace facial embeddings are encrypted using AES-256 GCM before storing in SQLite. No raw biometric face templates are saved.
- **🕒 Tri-Window Automated Burst Capture:** Monitors 1-hour timetable slots and triggers 3 automated 5-minute camera burst sessions:
  - **Window A (First 5 Mins):** Mins `00 - 05` of slot (e.g. `09:00 - 09:05`)
  - **Window B (Middle 5 Mins):** Mins `27 - 32` of slot (e.g. `09:27 - 09:32`)
  - **Window C (Last 5 Mins):** Mins `55 - 60` of slot (e.g. `09:55 - 10:00`)
- **🗳️ 2-out-of-3 Majority Voting Attendance Logic:**
  - **`PRESENT`**: Student detected in **at least 2 out of 3 windows** (`wins_present >= 2`).
  - **`PARTIAL`**: Student detected in **only 1 window** (`wins_present == 1`).
  - **`ABSENT`**: Student detected in **0 windows** (`wins_present == 0`).
- **🛡️ CLAHE Multi-Spectral Anti-Spoofing (PAD):**
  - **2D Fast Fourier Transform (FFT) Moiré Pattern Analysis:** Detects periodic subpixel screen grids.
  - **Specular Glass Glare & RGB Backlight Glow Filter:** Prevents spoofing via smartphone/tablet screens or printed photos.
  - **CLAHE Lighting Normalization:** Guarantees zero false rejections for real human faces under dim, warm, or overhead fluorescent lighting.
- **📱 Installable PWA Web Dashboard:** Modern dark mode interface with offline Service Worker support, instant 4-digit PIN authentication, real-time student/staff enrollment, interactive timetable manager with OCR parsing, and 1-click Excel exports.
- **🪪 Dedicated Staff Credentials & Biometric Directory:** Manage staff PIN codes, teaching roles, and daily staff attendance matrices.

---

## 🛠️ Technology Stack

- **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy ORM, SQLite
- **Biometrics & Computer Vision:** InsightFace (buffalo_l), OpenCV, NumPy, PyCryptodome (AES-256 GCM)
- **Frontend:** HTML5, CSS3 (Custom Glassmorphism), Modern JavaScript (ES Modules), FontAwesome 6, Service Workers (PWA)
- **Reports:** Pandas, OpenPyXL

---

## 🚀 Quick Start & Installation

### 1. Clone Repository & Install Dependencies
```bash
git clone https://github.com/realksquare/vtmt-attendance-system.git
cd vtmt-attendance-system

pip install -r requirements.txt
```

### 2. Launch FastAPI Web Server
```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```
Open your browser at: **`http://127.0.0.1:8000`**

- **Staff Login PIN:** `1234` or `5678`
- **Admin Login PIN:** `9999`

---

## 🧪 System Integration Test Suite

Run the full system verification test suite validating AES-256 GCM encryption roundtrips, Cosine similarity, 3-Window 2-out-of-3 voting, Anti-Spoofing PAD, and manual overrides:

```bash
python test_system.py
```

---

## 📄 License
Academic Final Year Project (FYP). Built with ❤️ for Smart Campus Attendance Management.
