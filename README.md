# AgentTrader AI 🚀

AgentTrader AI is a hybrid algorithmic trading system that combines classic technical analysis (Price Action) with a Machine Learning "Filter" to increase trade probability.

## 🧠 Core Philosophy
The system operates on a "Safety First" principle:
1.  **Rules-Based Generation**: A Python engine scans MT4 data for high-probability setups (Pin Bars, Engulfing Candles, FVGs, Trend Alignment).
2.  **AI Validation**: A Random Forest classifier (the "AI Brain") analyzes 40+ features of each setup to decide if it's a "Real Move" or a "Market Trap."
3.  **Execution**: Signals are sent back to MT4 only if both the Rules and the AI agree.

## 🛠 Project Structure
-   `agent_trader/strategy/`: Core logic for identifying trade candidates.
-   `agent_trader/ml/`: Machine learning models and training pipelines.
-   `agent_trader/features/`: Feature engineering (converts price data into AI-readable patterns).
-   `mt4_ea/`: The MetaTrader 4 Expert Advisor that exports data and executes signals.
-   `models/`: Stores your trained AI models (`.joblib`).

## 🚀 Getting Started

### 1. Data Export
Attach the `AgentTrader_Master` EA to your MT4 charts (M15, H1, and H4). It will export CSV data to the `data/` folder.

### 2. Training the AI
If you are running the bot for the first time or have added new historical data:
```bash
run train_initial.bat
```
This will process your MT4 history and create a custom AI model tailored to your specific pair and broker.

### 3. Live Trading
```bash
run start_trading.bat
```
The bot will now listen for new data from MT4, filter it through the AI, and send back `BUY`/`SELL` signals.

## 📊 Key Features
-   **London Session Filter**: Optimized for London session volatility.
-   **Confluence Scoring**: Combines multiple technical indicators into a single "Confidence" metric.
-   **Automated Retraining**: Easily update your AI model as market conditions change.
-   **Risk Management**: Built-in logic for Stop Loss (SL) and Take Profit (TP) calculation based on ATR and structure.

---
*Disclaimer: Trading involves risk. This software is for educational and assistant purposes only.*
