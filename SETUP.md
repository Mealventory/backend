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

uvicorn main:app --reload --host 0.0.0.0 --port 8000

Service URL:

http://127.0.0.1:8000

## 6) If py command is not found

Reopen terminal, then try:

C:\Users\<your-user>\AppData\Local\Programs\Python\Python311\python.exe --version

If that works, reinstall Python 3.11.9 and ensure PATH + py launcher were selected.