python -m venv venv
source venv/bin/activate      # Mac/Linux
venv\Scripts\activate         # Windows powershell not cmd

pip install -r requirements.txt

(First Time)
python.exe -m pip install --upgrade pip
pip install httpx[cli] 