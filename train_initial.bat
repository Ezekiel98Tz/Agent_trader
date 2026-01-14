@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   AgentTrader AI - Initial Model Trainer
echo ===================================================
echo.

:: 1. Get Symbol
set "SYMBOL=%~1"
if "%SYMBOL%"=="" (
    set /p "SYMBOL=Enter Symbol to train (e.g., GBPUSD, USDCAD): "
)

:: Clean the input
if defined SYMBOL set "SYMBOL=%SYMBOL: =%"
if "%SYMBOL%"=="" set "SYMBOL=GBPUSD"

:: 2. Setup Paths
set "MT4_BASE=%APPDATA%\MetaQuotes\Terminal\Common\Files\agent_trader"
set "DATA_DIR=%MT4_BASE%"

:: Check if data is in a subfolder
if exist "%MT4_BASE%\data\%SYMBOL%*_M15.csv" (
    set "DATA_DIR=%MT4_BASE%\data"
)

echo [INFO] Searching in: "%DATA_DIR%"

:: 3. Find the files and the suffix
set "ACTUAL_SYMBOL="
for /f "delims=" %%F in ('dir /b "%DATA_DIR%\%SYMBOL%*_M15.csv" 2^>nul') do (
    set "FULL_NAME=%%F"
    set "ACTUAL_SYMBOL=!FULL_NAME:_M15.csv=!"
)

if "%ACTUAL_SYMBOL%"=="" (
    echo [ERROR] Could not find any CSV files for %SYMBOL%
    echo Please make sure the EA is running on the MT4 chart.
    goto :end_pause
)

echo [INFO] Detected Symbol with Suffix: %ACTUAL_SYMBOL%
echo [INFO] Preparing to train...

:: 4. Define Files
set "H4_FILE=%DATA_DIR%\%ACTUAL_SYMBOL%_H4.csv"
set "H1_FILE=%DATA_DIR%\%ACTUAL_SYMBOL%_H1.csv"
set "M15_FILE=%DATA_DIR%\%ACTUAL_SYMBOL%_M15.csv"
set "OUT_MODEL=models\%SYMBOL%_model.joblib"

:: Verify files exist before running Python
if not exist "%H4_FILE%" ( echo [ERROR] Missing H4 file: %H4_FILE% && goto :end_pause )
if not exist "%H1_FILE%" ( echo [ERROR] Missing H1 file: %H1_FILE% && goto :end_pause )
if not exist "%M15_FILE%" ( echo [ERROR] Missing M15 file: %M15_FILE% && goto :end_pause )

echo [INFO] Starting Python Training Pipeline...
echo.

python -m agent_trader.pipelines.train ^
  --h4 "%H4_FILE%" ^
  --h1 "%H1_FILE%" ^
  --m15 "%M15_FILE%" ^
  --symbol "%SYMBOL%" ^
  --out-model "%OUT_MODEL%" ^
  --calibration sigmoid

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The AI training failed.
    echo This usually happens if there isn't enough history on the chart.
    echo Tip: Go to MT4, click the chart, and hold the 'Home' key for 30 seconds.
) else (
    echo.
    echo ===================================================
    echo   SUCCESS: Training Complete for %SYMBOL%
    echo ===================================================
    echo Your AI model is saved at: %OUT_MODEL%
)

:end_pause
echo.
echo ---------------------------------------------------
echo Script finished. Press any key to close this window.
pause
exit /b
