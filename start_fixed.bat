@echo off
cd /d "D:\New folder\leather-shoes-wms"
python -c "import database; database.init_db()"
uvicorn app:app --host 0.0.0.0 --port 5000
pause