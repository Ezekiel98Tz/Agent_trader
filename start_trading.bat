@echo off
setlocal enabledelayedexpansion

:: 1. Symbol Configuration
set "SYMBOL=%~1"
if "%SYMBOL%"=="" (
    set /p "SYMBOL=Enter Symbol to trade (e.g., GBPUSD, USDCAD): "
)
:: Remove any spaces from the input
if defined SYMBOL set "SYMBOL=%SYMBOL: =%"
if "%SYMBOL%"=="" set "SYMBOL=GBPUSD"

:: 2. Paths
set "MT4_DATA=%APPDATA%\MetaQuotes\Terminal\Common\Files\agent_trader"
set "DATA_DIR=%MT4_DATA%"
set "SIGNALS_DIR=%MT4_DATA%\inbox"
set "MODEL=models\%SYMBOL%_model.joblib"

echo ===================================================
echo   AgentTrader AI - Trading Service [%SYMBOL%]
echo ===================================================

:: Detect actual filename (handling suffixes like USDCADb)
set "ACTUAL_SYMBOL="
if exist "%DATA_DIR%\data\%SYMBOL%*_M15.csv" set "DATA_DIR=%MT4_DATA%\data"

for /f "delims=" %%F in ('dir /b "%DATA_DIR%\%SYMBOL%*_M15.csv" 2^>nul') do (
    set "FILENAME=%%F"
    set "ACTUAL_SYMBOL=!FILENAME:_M15.csv=!"
    goto :found
)

:found
if "%ACTUAL_SYMBOL%"=="" (
    echo [ERROR] No data found for %SYMBOL% at %DATA_DIR%\
    echo Please make sure AgentTrader_Master.mq4 is running on an MT4 chart for %SYMBOL%.
    pause
    exit /b
)

:: 3. Check for Model
if not exist "%MODEL%" (
    echo [WARNING] AI Model for %SYMBOL% not found at %MODEL%
    echo.
    set /p "TRAIN_NOW=Would you like to train it now? (y/n): "
    if /i "!TRAIN_NOW!"=="y" (
        call train_initial.bat "%SYMBOL%"
        if %errorlevel% neq 0 (
            echo [ERROR] Training failed or was cancelled.
            pause
            exit /b 1
        )
        :: Refresh data dir and actual symbol after training
        set "DATA_DIR=%MT4_DATA%"
        if exist "%DATA_DIR%\data\%SYMBOL%*_M15.csv" set "DATA_DIR=%MT4_DATA%\data"
        for /f "delims=" %%F in ('dir /b "!DATA_DIR!\%SYMBOL%*_M15.csv" 2^>nul') do (
            set "FILENAME=%%F"
            set "ACTUAL_SYMBOL=!FILENAME:_M15.csv=!"
        )
    ) else (
        echo [ERROR] Cannot start trading without an AI model.
        pause
        exit /b
    )
)

:: 4. Start Trading Service
echo [INFO] Starting trading for %SYMBOL% using data for %ACTUAL_SYMBOL%
python -m agent_trader.runtime.service ^
  --source csv ^
  --h4  "%DATA_DIR%\%ACTUAL_SYMBOL%_H4.csv" ^
  --h1  "%DATA_DIR%\%ACTUAL_SYMBOL%_H1.csv" ^
  --m15 "%DATA_DIR%\%ACTUAL_SYMBOL%_M15.csv" ^
  --symbol "%ACTUAL_SYMBOL%" ^
  --model "%MODEL%" ^
  --out-dir "%SIGNALS_DIR%" ^
  --interval-seconds 60 ^
  --mode live

echo.
echo [INFO] Trading service has stopped.
pause
