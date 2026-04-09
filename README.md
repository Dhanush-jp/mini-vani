# AI-Powered Student Intelligence System

Monorepo structure:

- `backend/` - FastAPI + SQLAlchemy + MySQL + JWT + Excel export
- `frontend/` - React + Vite + Tailwind + Framer Motion + Recharts
- `ml-service/` - optional FastAPI service for `/predict-risk`

## 1. Prerequisites

Install these before running the project:

- Python 3.11 or newer
- Node.js 20 or newer
- MySQL 8.x

Check versions:

```powershell
python --version
node --version
npm --version
mysql --version
```

## 2. Clone Or Open The Project

Open a terminal in:

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani"
```

## 3. MySQL Setup

Make sure MySQL is running.

Create the database user if needed, or use your existing root account.

The backend will create the database automatically if it does not exist, but MySQL itself must already be running.

## 4. Backend Setup

Open a new terminal:

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\backend"
```

Create a virtual environment if you do not already have one:

```powershell
python -m venv venv
```

Activate it:

```powershell
venv\Scripts\activate
```

Install backend dependencies:

```powershell
pip install -r requirements.txt
```

Create or update `backend/.env`.

Example:

```env
APP_NAME=AI-Powered Student Intelligence System
API_V1_PREFIX=/api/v1
DEBUG=false

DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=root
DB_NAME=student_intelligence

SECRET_KEY=replace-with-strong-key
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=120

ML_SERVICE_URL=http://localhost:8001
GROQ_API_KEY=paste_your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_ENDPOINT=https://api.groq.com/openai/v1/chat/completions
GROQ_TIMEOUT_SECONDS=45
```

Groq key paste location:

- Main backend Excel import flow: `backend/.env`
- Separate Groq ingestion service: `excel_ingestion_service/.env`

Paste it exactly like this:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Run the backend:

```powershell
python main.py
```

Backend URLs:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## 5. Frontend Setup

Open another terminal:

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\frontend"
```

Install frontend dependencies:

```powershell
npm install
```

Run the frontend:

```powershell
npm run dev
```

Frontend URL:

- App: `http://localhost:5173`

## 6. Seed Demo Data

Seed command creates:

- 1 admin
- 10 teachers
- 600 students
- teacher-student mapping
- assigned subjects
- grades
- attendance
- SGPA, CGPA, backlogs
- risk analysis

Open a terminal:

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\backend"
venv\Scripts\activate
python seed_data.py
```

Important:

- This script writes demo data into the configured MySQL database.
- It clears previous seeded `@college.com` records before inserting fresh seed data.

## 7. Optional ML Service Setup

This is only needed if you want the `/student/me/predict-risk` API to call the separate ML service.

Open another terminal:

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\ml-service"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

ML service URL:

- `http://localhost:8001`

## 8. Recommended Run Order

Use this order every time for a clean local setup:

1. Start MySQL
2. Start backend
3. Run seed data if you want demo records
4. Start frontend
5. Start ML service only if you need risk prediction API

## 9. Full Command List

### Backend first-time setup

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\backend"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Backend later runs

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\backend"
venv\Scripts\activate
python main.py
```

### Seed data

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\backend"
venv\Scripts\activate
python seed_data.py
```

### Frontend first-time setup

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\frontend"
npm install
npm run dev
```

### Frontend later runs

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\frontend"
npm run dev
```

### Frontend production build

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\frontend"
npm run build
```

### Optional ML service

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\ml-service"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 10. Seeded Login Accounts

After running `python seed_data.py`:

- Admin: `admin@college.com`
- Teachers: `teacher1@college.com` to `teacher10@college.com`
- Students: `student1@college.com` to `student600@college.com`

Default password for seeded users:

```text
Password@123
```

## 11. Common Issues

### Backend does not start

Check:

- MySQL is running
- `backend/.env` has correct DB values
- virtual environment is activated
- dependencies are installed

### Frontend cannot reach backend

Make sure backend is running on:

```text
http://localhost:8000
```

### Seed command fails

Check:

- backend is configured to the correct MySQL database
- MySQL is running
- backend dependencies are installed

### New tables are missing

Restart the backend after pulling changes:

```powershell
cd "c:\Users\chdha\OneDrive\Desktop\min vani\backend"
venv\Scripts\activate
python main.py
```

## 12. Current Main Features

- role-based authentication
- teacher-student mapping through `teacher_students`
- admin student creation with teacher selection
- teacher student creation with automatic teacher assignment
- routed SaaS-style UI
- attendance management
- results management
- student-subject assignment
- analytics with SGPA, CGPA, backlogs, risk
- Excel export
- large demo seed dataset
