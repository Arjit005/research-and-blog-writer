@echo off
echo ============================================
echo   Research & Blog Writer - Auto Setup
echo ============================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+ first.
    pause
    exit /b 1
)

:: Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
) else (
    echo [1/3] Virtual environment already exists. Skipping.
)

:: Activate venv
echo [2/3] Activating virtual environment...
call .venv\Scripts\activate.bat

:: Install dependencies (try uv first, fallback to pip)
echo [3/3] Installing all dependencies...
where uv >nul 2>&1
if %errorlevel% equ 0 (
    uv pip install -r requirements.txt
) else (
    if exist ".venv\Scripts\uv.exe" (
        .venv\Scripts\uv.exe pip install -r requirements.txt
    ) else (
        pip install -r requirements.txt
    )
)

echo.
echo ============================================
echo   Setup complete! To run the app:
echo     .venv\Scripts\activate
echo     streamlit run app.py
echo ============================================
pause
