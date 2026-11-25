@echo off
setlocal
set "RAIZ=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%RAIZ%scripts\instalar_windows.ps1" %*
if errorlevel 1 (
    echo.
    echo [ERROR] La instalacion no se pudo completar.
    pause
    exit /b 1
)
endlocal
