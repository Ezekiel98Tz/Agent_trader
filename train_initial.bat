@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   AgentTrader AI - Initial Model Trainer
echo ===================================================
echo.

:: Configuration
set MT4_DATA=%APPDATA%\MetaQuotes\Terminal\Common\Files\agent_trader
set OUT_MODEL=models/production_model.joblib

:: Check if data exists
if not exist "%MT4_DATA%\data\GBPUSD_M15.csv" (
    echo [ERROR] No data found at %MT4_DATA%\data\
    echo Please make sure AgentTrader_Master.mq4 is running on an MT4 chart.
    pause
    exit /b
)

echo [INFO] Data found. Starting training pipeline...
echo [INFO] This will create: %OUT_MODEL%
echo.

python -m agent_trader.pipelines.train ^
  --h4  "%MT4_DATA%\data\GBPUSD_H4.csv" ^
  --h1  "%MT4_DATA%\data\GBPUSD_H1.csv" ^
  --m15 "%MT4_DATA%\data\GBPUSD_M15.csv" ^
  --out-model "%OUT_MODEL%" ^
  --calibration sigmoid

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Training failed. Check if you have enough bars in your MT4 chart.
    pause
    exit /b
)

echo.
echo ===================================================
echo   TRAINING COMPLETE!
echo ===================================================
echo Your AI brain is now ready.
echo You can now run 'start_trading.bat' to begin live trading.
echo ===================================================
if "%~1"=="--no-pause" exit /b 0
pause
