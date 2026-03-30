# Backend Setup (Python 3.11.9)

## 1) Install Python 3.11.9

- Official download page: https://www.python.org/downloads/release/python-3119/
- Download: Windows installer (64-bit)
- During installation, enable:
	- Add python.exe to PATH
	- Install launcher for all users (py launcher)

## 2) Verify Python on your machine

Run these commands from a new terminal:

py -3.11 --version
py -0p

Expected: Python 3.11.9 is listed.

## 3) Create and activate virtual environment

From project root (Capstone):

cd backend
py -3.11 -m venv .venv

PowerShell:

.\.venv\Scripts\Activate.ps1

CMD:

.\.venv\Scripts\activate.bat

## 4) Install dependencies

python -m pip install --upgrade pip
pip install -r requirements.txt

## 5) Run the backend

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Service URL:

http://127.0.0.1:8000

## 6) If py command is not found

Reopen terminal, then try:

C:\Users\<your-user>\AppData\Local\Programs\Python\Python311\python.exe --version

If that works, reinstall Python 3.11.9 and ensure PATH + py launcher were selected.

## 7) Test without frontend using backend/samples

1. Put .jpg/.jpeg images into backend/samples (for example food_(1).jpg, receipt_(1).jpg, tag_(1).jpg).
2. Ensure backend .env includes:

ENABLE_SAMPLE_SCAN=true
SAMPLE_IMAGES_DIR=samples

3. Run ai-service on port 8001 and backend on port 8000.
4. Call sample endpoint from backend terminal:

curl -X POST http://127.0.0.1:8000/api/v1/scan/sample \
	-H "Content-Type: application/json" \
	-d "{\"sample_name\":\"food_(1).jpg\",\"mode\":\"food\",\"persist_to_db\":false}"

If you want to store in DB, set persist_to_db=true and provide user_id:

curl -X POST http://127.0.0.1:8000/api/v1/scan/sample \
	-H "Content-Type: application/json" \
	-d "{\"sample_name\":\"receipt_(1).jpg\",\"mode\":\"receipt\",\"persist_to_db\":true,\"user_id\":\"your-user-id\"}"