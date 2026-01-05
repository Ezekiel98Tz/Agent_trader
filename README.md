# AgentTrader AI 🚀

AgentTrader AI is a high-performance, hybrid algorithmic trading system. It bridges the gap between **Classic Price Action** and **Modern Machine Learning**, using Python as the "Brain" and MetaTrader 4 (MT4) as the "Eyes and Hands."

---

## 🏗 How It Works: The 5 Stages

Our project follows a strictly modular workflow to ensure safety and precision.

### **Stage 1: Data Acquisition (The Eyes)**
The `AgentTrader_Master` EA sits on your MT4 terminal. Every 60 seconds, it "takes a snapshot" of the market by exporting historical data for three timeframes (H4, H1, and M15) into CSV files.
- **Why?** This allows Python to see exactly what you see on your charts.

### **Stage 2: Candidate Generation (The Scanner)**
The Python engine scans the raw CSV data looking for specific **Rules-Based Setups**:
- **Trend Alignment**: Is the H4 and H1 trend moving in the same direction?
- **Price Action**: Are there Pin Bars or Engulfing Candles at key levels?
- **Market Structure**: Are we near a Support/Resistance zone or inside a Fair Value Gap (FVG)?
- **Result**: If these rules pass, a "Trade Candidate" is created.

### **Stage 3: Feature Engineering (The Context)**
The system doesn't just look at the candle; it looks at the **environment**. For every candidate, it calculates 40+ features:
- **EMA Slopes**: How aggressive is the trend?
- **Volatility (ATR)**: Is the market over-extended or quiet?
- **Session State**: Are we in the London Open, New York Overlap, or "Off-Hours"?
- **Confluence Score**: How many technical indicators agree on this move?

### **Stage 4: AI Validation (The Brain)**
This is where the magic happens. The candidate is passed to a **Random Forest Classifier** (your AI model). 
- The AI looks at how similar setups performed in the past.
- It predicts a **Probability Score** (e.g., 0.68 probability of a win).
- **Quality Filter**: The `decide_quality` logic checks the session (PRIMARY vs SECONDARY) and probability to decide if the risk is worth taking.

### **Stage 5: Signal Execution (The Hands)**
If the AI gives a "Green Light":
1. Python writes a `signal_XYZ.csv` file into the MT4 "Inbox."
2. The MT4 EA detects this file immediately.
3. It validates the risk (spread, daily loss limits, max trades).
4. **Execution**: It places the BUY/SELL order with precise SL and TP levels.

---

## 🛠 Project Architecture
- [generator.py](file:///c:/Users/hp/Documents/trae_projects/agent_trader/agent_trader/strategy/generator.py): The "Scanner" (Price Action rules).
- [model.py](file:///c:/Users/hp/Documents/trae_projects/agent_trader/agent_trader/ml/model.py): The "AI Brain" (Random Forest logic).
- [quality.py](file:///c:/Users/hp/Documents/trae_projects/agent_trader/agent_trader/policy/quality.py): The "Safety Officer" (Filters trades by session/probability).
- [service.py](file:///c:/Users/hp/Documents/trae_projects/agent_trader/agent_trader/runtime/service.py): The "Heartbeat" (Keeps the loop running).

---

## 🚀 Quick Start Guide

### 1. The Setup
Attach `AgentTrader_Master` to your MT4 charts (M15, H1, H4). Ensure **"Allow DLL Imports"** is checked.

### 2. The Training (Building the Brain)
Run the initial training to teach the AI about your broker's data:
```bash
run train_initial.bat
```

### 3. The Trading (Live Mode)
Launch the AI monitoring service:
```bash
run start_trading.bat
```

---

## 📊 Safety First Philosophy
- **London Session Focus**: The bot is most active during the London session (High Liquidity).
- **Dynamic Risk**: It automatically reduces lot sizes during the "Secondary" session or for "Average" quality setups.
- **Leakage Prevention**: Our training pipeline strictly removes "future data" to ensure the AI isn't cheating during backtests.

---
*Disclaimer: Trading involves risk. This software is for educational and assistant purposes only.*
