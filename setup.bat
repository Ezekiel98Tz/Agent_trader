@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   AgentTrader AI - One-Click Setup
echo ===================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+ and add it to PATH.
    pause
    exit /b
)
echo [OK] Python detected.

:: 2. Install Dependencies
echo [INFO] Installing Python dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b
)
echo [OK] Dependencies installed.

:: 3. Create Folders in Common\Files
echo [INFO] Creating MT4 data folders...
set MT4_COMMON=%APPDATA%\MetaQuotes\Terminal\Common\Files\agent_trader
mkdir "%MT4_COMMON%\data" >nul 2>&1
mkdir "%MT4_COMMON%\inbox" >nul 2>&1
echo [OK] Folders created at: %MT4_COMMON%

:: 4. Create Models folder
mkdir "models" >nul 2>&1
echo [OK] Models folder created.

echo.
echo ===================================================
echo   SETUP COMPLETE!
echo ===================================================
echo 1. Open MT4 MetaEditor (F4).
echo 2. Copy 'mt4_ea/AgentTrader_Master.mq4' to your Experts folder.
echo 3. Compile (F7) and attach to ONE GBPUSD chart.
echo 4. Wait 1 minute for data to export, then run 'train_initial.bat'.
echo 5. Run 'start_trading.bat' to go live.
echo ===================================================
pause
