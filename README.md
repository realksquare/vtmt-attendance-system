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
- **🛡️ Hybrid Offline Anti-Spoofing (PAD) & Multi-Frame Aggregator:**
  - **Local MiniFASNet V2 & V1SE ONNX Inference:** Evaluates physical presentation attacks (printed photos, phone screens, monitors, and cutouts) offline on local CPU.
  - **Multi-Frame Statistical Aggregator:** Enforces multi-observation temporal consistency (median score >= 0.70) across tracks to prevent single-frame false acceptances.
  - **Fail-Closed Security Gate:** Ensures model errors or unavailable models never authorize attendance.
- **👁️ 3-Tier Face Quality & Multi-Face Classroom Tracking:**
  - **3-Tier Quality Hierarchy:** Categorizes faces into `RECOGNITION_SAFE` (front/mid rows), `TRACKABLE_BUT_SMALL` (back rows & suboptimal lighting), and `UNUSABLE` (severe blur or clipping).
  - **Spatial-Temporal Multi-Face Tracker:** Simultaneously tracks multiple seated students across sample frames with non-blocking threaded camera acquisition.
  - **Atomic Burst-Level Voting:** Accumulates candidate identity observations across the window and commits attendance once per window.
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
