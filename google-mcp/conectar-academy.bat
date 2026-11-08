@echo off
rem (Opcional) Renueva la conexion de academy@bryangibe.com. Se abre el navegador.
set "D=%USERPROFILE%\mcp-bryan-gibe"
if not exist "%D%\server.py" set "D=%USERPROFILE%\google-mcp"
if not exist "%D%\server.py" set "D=%~dp0"
cd /d "%D%"
where py >nul 2>nul
if %errorlevel%==0 (py -3 get_refresh_token.py academy) else (python get_refresh_token.py academy)
echo.
echo Reinicia Claude para usar la cuenta.
pause
