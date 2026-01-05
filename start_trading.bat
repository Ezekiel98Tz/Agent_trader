@echo off
echo ===================================================
echo   AgentTrader AI - Production Runner
echo ===================================================
echo.

:: Configuration
set MODEL_PATH=models/production_model.joblib
set MT4_DATA=%APPDATA%\MetaQuotes\Terminal\Common\Files\agent_trader

:: Check if model exists
if not exist "%MODEL_PATH%" (
    echo [ERROR] AI Model not found at %MODEL_PATH%
    echo Please run 'train_initial.bat' first to build your AI brain.
    pause
    exit /b
)

echo [INFO] Starting AI Service...
echo [INFO] Data Source: %MT4_DATA%\data
echo [INFO] Signal Inbox: %MT4_DATA%\inbox
echo.

python -m agent_trader.runtime.service ^
  --source csv ^
  --h4  "%MT4_DATA%\data\GBPUSD_H4.csv" ^
  --h1  "%MT4_DATA%\data\GBPUSD_H1.csv" ^
  --m15 "%MT4_DATA%\data\GBPUSD_M15.csv" ^
  --model "%MODEL_PATH%" ^
  --out-dir "%MT4_DATA%\inbox" ^
  --mode live ^
  --interval-seconds 60

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] AI Service crashed. Checking logs...
    pause
)
