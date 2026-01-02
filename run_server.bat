@echo off
echo Iniciando AutoServer Deployer...
echo Acesse o painel em: http://localhost:8000
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
