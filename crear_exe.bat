@echo off
python -m pip install pyinstaller
pyinstaller --onefile --windowed --name SaltoConsulta SaltoConsulta.pyw
pause
