@echo off
echo ============================================
echo   Research & Blog Writer - Auto Setup
echo ============================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10 - 3.13 first.
    pause
    exit /b 1
)

:: Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
) else (
    echo [1/4] Virtual environment already exists. Skipping.
)

:: Activate venv
echo [2/4] Activating virtual environment...
call .venv\Scripts\activate.bat

:: Install Python dependencies (try uv first, fallback to pip)
echo [3/4] Installing Python dependencies...
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

:: Install frontend dependencies if Node.js is available
where node >nul 2>&1
if %errorlevel% equ 0 (
    echo [4/4] Installing Next.js frontend dependencies...
    pushd frontend
    call npm ci
    popd
) else (
    echo [4/4] Node.js not found. Skipping frontend dependencies.
    echo       The Next.js UI requires Node.js 20.9+; the legacy Streamlit UI works without it.
)

echo.
echo ============================================
echo   Setup complete! To run the app:
echo.
echo   Terminal 1 (API):
echo     .venv\Scripts\activate
echo     uvicorn backend.main:app --reload --port 8000
echo.
echo   Terminal 2 (Next.js UI):
echo     cd frontend
echo     set NEXT_PUBLIC_API_BASE=http://localhost:8000
echo     npm run dev
echo.
echo   Legacy Streamlit UI (deprecated, local only):
echo     streamlit run app.py
echo ============================================
pause
