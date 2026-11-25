@echo off
setlocal
set "RAIZ=%~dp0"
set "PY_EMB=%RAIZ%runtime\python\python.exe"

if not exist "%PY_EMB%" (
    echo [GuarIdA] No se encontro Python embebido en runtime\python.
    echo [GuarIdA] Ejecutando instalacion automatica desde cero...
    call "%RAIZ%Instalar.bat"
    if errorlevel 1 (
        echo [ERROR] Fallo la instalacion automatica.
        pause
        exit /b 1
    )
)

set "PYTHONPATH=%RAIZ%app;%PYTHONPATH%"
"%PY_EMB%" -c "import psutil, cryptography, fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [GuarIdA] Dependencias incompletas. Completando instalacion...
    call "%RAIZ%Instalar.bat"
    if errorlevel 1 (
        echo [ERROR] Fallo la instalacion de dependencias.
        pause
        exit /b 1
    )
)

echo [GuarIdA] Iniciando como servicio en red local (0.0.0.0:8080)...
"%PY_EMB%" "%RAIZ%app\main.py" --web --host 0.0.0.0 --port 8080 --no-browser %*
if errorlevel 1 (
    echo.
    echo [GuarIdA] El servicio termino con codigo de error %errorlevel%.
    pause
)
endlocal
