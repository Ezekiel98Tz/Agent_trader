#property copyright "Copyright 2026, Ezekiel98Tz"
#property link      "https://github.com/Ezekiel98Tz/Agent_trader"
#property version   "2.00"
#property strict

//--- AI Configuration
input string   _header_ai            = "--- AI SETTINGS ---";
input bool     AutoTrade             = false;  // Allow execution of trades?
input bool     VisualOnly            = true;   // Only show signals in logs, no trades
input int      ExportIntervalSeconds = 60;     // Sync data with AI every X seconds
input string   InboxSubdir           = "agent_trader\\inbox"; 
input string   DataSubdir            = "agent_trader\\data";

//--- Risk Management
input string   _header_risk          = "--- RISK SETTINGS ---";
input double   Lots                  = 0.10;   
input int      SlippagePoints        = 20;     
input int      MagicNumber           = 240102; 
input int      MaxTradesPerDay       = 3;      
input double   MaxDailyLossMoney     = 50.0;   
input double   MaxSpreadPips         = 2.5;    

//--- Trade Management
input string   _header_mgmt          = "--- TRADE MGMT ---";
input bool     BreakEvenEnabled      = true;   
input double   BreakEvenTriggerPips  = 10.0;   
input bool     TrailingEnabled       = false;  
input double   TrailingPips          = 12.0;   
input int      DayCloseHour          = 21;     
input int      DayCloseMinute        = 30;     

//--- Global Variables
string g_last_signal_id = "";
datetime g_last_export = 0;
datetime g_last_heartbeat = 0;
string g_ai_status = "Waiting for Sync...";
string g_market_regime = "Analyzing...";

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("AgentTrader Master EA Initialized.");
   _create_dashboard();
   // Create directories in Common\Files
   int h = FileOpen(DataSubdir + "\\init.txt", FILE_WRITE|FILE_TXT|FILE_COMMON);
   if(h != INVALID_HANDLE) FileClose(h);
   h = FileOpen(InboxSubdir + "\\init.txt", FILE_WRITE|FILE_TXT|FILE_COMMON);
   if(h != INVALID_HANDLE) FileClose(h);
   
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, "AT_");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // 1. DATA EXPORT (The "Eyes")
   if(TimeCurrent() - g_last_export >= ExportIntervalSeconds)
   {
      if(_export_all()) {
         g_last_export = TimeCurrent();
         g_ai_status = "Data Synced: " + TimeToStr(g_last_export, TIME_MINUTES|TIME_SECONDS);
      } else {
         g_ai_status = "Sync Error!";
      }
   }

   // 2. MANAGEMENT (The "Brain")
   ApplyManagement();
   CloseAtCutoff();

   // 3. SIGNAL PROCESSING (The "Hands")
   string id, symbol, side, session_state, regime, quality, mode, filename;
   datetime t_utc;
   double entry, sl, tp, confluence, prob, risk_mult;

   // Heartbeat log every 60 seconds
   if(TimeCurrent() - g_last_heartbeat >= 60)
   {
      Print("[AgentTrader] Scanning for signals in: ", InboxSubdir, "...");
      g_last_heartbeat = TimeCurrent();
   }

   if(ReadNextSignal(id, t_utc, symbol, side, entry, sl, tp, confluence, prob, session_state, regime, quality, risk_mult, mode, filename))
   {
      g_market_regime = regime;
      
      // 1. Check if it's already the last one we saw
      if(id == g_last_signal_id)
      {
         MarkSignalConsumed(filename);
         return;
      }
      
      // 2. Check if signal is too old (> 15 mins)
      // Comparison using Broker Time (TimeCurrent) for perfect sync with exported data
      datetime now_broker = TimeCurrent();
      if(now_broker - t_utc > 900) // 15 minutes
      {
         Print("[AgentTrader] Signal ", id, " is too old (", (now_broker - t_utc), "s). Expiring...");
         MarkSignalConsumed(filename);
         return;
      }

      // 3. Process the trade (ReadNextSignal already filtered for symbol match)
      g_last_signal_id = id;
      Print("[AgentTrader] New Signal Detected: ", side, " ", symbol, " @ ", entry, " (ID: ", id, ")");
      _process_trade(side, entry, sl, tp, prob, risk_mult, quality, mode, filename);
   }

   _update_dashboard();
}

//+------------------------------------------------------------------+
//| Logic Functions                                                  |
//+------------------------------------------------------------------+

bool _export_all()
{
   bool ok = true;
   ok &= _export_tf(Symbol(), PERIOD_H4, 500);
   ok &= _export_tf(Symbol(), PERIOD_H1, 800);
   ok &= _export_tf(Symbol(), PERIOD_M15, 1500);
   return ok;
}

bool _export_tf(string sym, int tf, int count)
{
   string tf_name = (tf==PERIOD_H4)?"H4":((tf==PERIOD_H1)?"H1":"M15");
   string filename = DataSubdir + "\\" + sym + "_" + tf_name + ".csv";
   int handle = FileOpen(filename, FILE_WRITE|FILE_CSV|FILE_COMMON, ',');
   if(handle == INVALID_HANDLE) return false;
   FileWrite(handle, "time", "open", "high", "low", "close", "tick_volume");
   for(int i = count - 1; i >= 0; i--)
   {
      FileWrite(handle, 
         TimeToStr(iTime(sym, tf, i), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
         DoubleToStr(iOpen(sym, tf, i), Digits),
         DoubleToStr(iHigh(sym, tf, i), Digits),
         DoubleToStr(iLow(sym, tf, i), Digits),
         DoubleToStr(iClose(sym, tf, i), Digits),
         IntegerToString(iVolume(sym, tf, i))
      );
   }
   FileClose(handle);
   return true;
}

void _process_trade(string side, double entry, double sl, double tp, double prob, double risk_mult, string quality, string mode, string filename)
{
   bool do_trade = AutoTrade && !VisualOnly && (mode == "live" || mode == "paper") && (quality != "SKIP");
   
   if(!AutoTrade) Print("[AgentTrader] Trade SKIPPED: 'AutoTrade' is set to false in EA inputs.");
   if(VisualOnly) Print("[AgentTrader] Trade SKIPPED: 'VisualOnly' mode is enabled.");
   if(quality == "SKIP") Print("[AgentTrader] Trade SKIPPED: AI Quality logic returned 'SKIP'.");

   int trades_today = GetTradesToday();
   double daily_pnl = AccountBalance() - GetStartBalance();
   double spread = (Ask - Bid) / _pip();

   if(trades_today >= MaxTradesPerDay)
   {
      Print("[AgentTrader] Trade SKIPPED: MaxTradesPerDay (", MaxTradesPerDay, ") reached.");
      do_trade = false;
   }
   if(MaxDailyLossMoney > 0 && daily_pnl <= -MaxDailyLossMoney)
   {
      Print("[AgentTrader] Trade SKIPPED: MaxDailyLossMoney (", MaxDailyLossMoney, ") reached.");
      do_trade = false;
   }
   if(spread > MaxSpreadPips)
   {
      Print("[AgentTrader] Trade SKIPPED: Current Spread (", spread, ") exceeds MaxSpreadPips (", MaxSpreadPips, ").");
      do_trade = false;
   }

   if(do_trade)
   {
      int cmd = (side == "buy") ? OP_BUY : OP_SELL;
      double price = (cmd == OP_BUY) ? Ask : Bid;
      double sl_n = NormalizeDouble(sl, Digits);
      double tp_n = NormalizeDouble(tp, Digits);
      
      if(_stops_valid(cmd == OP_BUY, sl_n, tp_n))
      {
         Print("[AgentTrader] Attempting to Open ", side, " Order...");
         int ticket = OrderSend(Symbol(), cmd, Lots * risk_mult, price, SlippagePoints, sl_n, tp_n, "AgentTrader", MagicNumber, 0, (cmd == OP_BUY ? clrBlue : clrRed));
         if(ticket > 0) 
         {
            Print("[AgentTrader] Trade OPENED Successfully! Ticket: ", ticket);
            IncTradesToday();
         }
         else {
            Print("[AgentTrader] Trade FAILED. Error Code: ", GetLastError());
         }
      }
      else {
         Print("[AgentTrader] Trade SKIPPED: Invalid Stops (SL: ", sl_n, ", TP: ", tp_n, "). Check Broker StopLevels.");
      }
   }
   MarkSignalConsumed(filename);
}

//+------------------------------------------------------------------+
//| Dashboard UI                                                     |
//+------------------------------------------------------------------+
void _create_dashboard()
{
   _label("AT_Title", "AgentTrader AI v2.0", 10, 20, 14, clrGold);
   _label("AT_Status", "Status: Initializing...", 10, 45, 10, clrWhite);
   _label("AT_Regime", "Regime: Analyzing...", 10, 65, 10, clrCyan);
   _label("AT_Risk", "Daily Trades: 0", 10, 85, 10, clrWhite);
}

void _update_dashboard()
{
   ObjectSetString(0, "AT_Status", OBJPROP_TEXT, "AI Status: " + g_ai_status);
   ObjectSetString(0, "AT_Regime", OBJPROP_TEXT, "Market Regime: " + g_market_regime);
   ObjectSetString(0, "AT_Risk", OBJPROP_TEXT, "Trades Today: " + IntegerToString(GetTradesToday()) + " / " + IntegerToString(MaxTradesPerDay));
   
   color c = (g_market_regime == "TREND") ? clrLime : (g_market_regime == "RANGE" ? clrYellow : clrOrange);
   ObjectSetInteger(0, "AT_Regime", OBJPROP_COLOR, c);
}

void _label(string name, string text, int x, int y, int size, color col)
{
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, size);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
}

//+------------------------------------------------------------------+
//| Core Utilities (Include previously defined helpers)              |
//+------------------------------------------------------------------+
double _pip() { string s=Symbol(); return (StringLen(s)>=3 && StringSubstr(s,StringLen(s)-3,3)=="JPY")?0.01:0.0001; }
bool _stops_valid(bool b, double sl, double tp) { 
   double p = b?Ask:Bid; double min = MarketInfo(Symbol(), MODE_STOPLEVEL)*Point;
   if(b) return (sl < p && tp > p && (p-sl)>=min && (tp-p)>=min);
   return (sl > p && tp < p && (sl-p)>=min && (p-tp)>=min);
}

// (Include GetTradesToday, GetStartBalance, IncTradesToday, ReadNextSignal, MarkSignalConsumed, ApplyManagement, CloseAtCutoff from previous code)
// Note: For brevity, I am assuming the user will paste the utility functions from the previous Signal EA.
// In the final version, I will provide the complete combined file.

// ... [Rest of utility functions from Signal EA] ...
bool ReadNextSignal(string &id, datetime &t_utc, string &symbol, string &side, double &entry, double &sl, double &tp, double &confluence, double &prob, string &session_state, string &regime, string &quality, double &risk_mult, string &mode, string &filename_out)
{
   string subdir = InboxSubdir;
   string current_sym = Symbol();
   
   // Search for signals that start with our symbol or generic 'signal_'
   // The new format is signal_SYMBOL_ID.csv
   long handle = FileFindFirst(subdir + "\\signal_*.csv", filename_out, FILE_COMMON);
   if(handle == INVALID_HANDLE) return false;
   
   bool found = false;
   while(true)
   {
      if(filename_out == "" || !FileIsExist(subdir + "\\" + filename_out, FILE_COMMON))
      {
         if(!FileFindNext(handle, filename_out)) break;
         continue;
      }
      
      // Check if this signal belongs to our symbol (flexible match)
      // signal_GBPUSD_123.csv matches chart GBPUSDb
      bool sym_match = (StringFind(filename_out, current_sym) >= 0 || StringFind(current_sym, symbol) >= 0);
      
      // If the filename contains another symbol's name, skip it (unless it's ours)
      // This prevents GBPUSD EA from consuming USDCAD signals
      if(!sym_match && StringFind(filename_out, "signal_") == 0)
      {
         // Extract symbol from filename signal_{SYMBOL}_{ID}.csv
         string file_parts[]; 
         ushort file_sep = StringGetCharacter("_", 0);
         if(StringSplit(filename_out, file_sep, file_parts) >= 2)
         {
             string file_sym = file_parts[1];
             if(file_sym != "" && StringFind(current_sym, file_sym) < 0 && StringFind(file_sym, current_sym) < 0)
             {
                 if(!FileFindNext(handle, filename_out)) break;
                 continue;
             }
         }
      }

      int fh = FileOpen(subdir + "\\" + filename_out, FILE_READ|FILE_COMMON|FILE_ANSI);
      if(fh == INVALID_HANDLE) { if(!FileFindNext(handle, filename_out)) break; continue; }
      string line = FileReadString(fh); FileClose(fh);
      string parts[]; ushort sep = StringGetCharacter(",", 0); int n = StringSplit(line, sep, parts);
      if(n < 14) { if(!FileFindNext(handle, filename_out)) break; continue; }
      
      id = parts[0]; 
      t_utc = (datetime)StringToTime(parts[1]); 
      symbol = parts[2]; 
      side = parts[3];
      entry = StringToDouble(parts[4]); 
      sl = StringToDouble(parts[5]); 
      tp = StringToDouble(parts[6]);
      confluence = StringToDouble(parts[7]); 
      prob = StringToDouble(parts[8]); 
      session_state = parts[9];
      regime = parts[10]; 
      quality = parts[11]; 
      risk_mult = StringToDouble(parts[12]); 
      mode = parts[13];
      
      // Final sanity check: is this signal for us?
      if(StringFind(symbol, current_sym) >= 0 || StringFind(current_sym, symbol) >= 0)
      {
         found = true; 
         break;
      }
      
      if(!FileFindNext(handle, filename_out)) break;
   }
   FileFindClose(handle); return found;
}

void MarkSignalConsumed(const string filename)
{
   string src = InboxSubdir + "\\" + filename;
   string dst = InboxSubdir + "\\consumed_" + filename;
   if(FileIsExist(src, FILE_COMMON)) FileMove(src, FILE_COMMON, dst, FILE_REWRITE);
}

string DayKey() { datetime now = TimeCurrent(); return IntegerToString(TimeYear(now)) + StringFormat("%02d", TimeMonth(now)) + StringFormat("%02d", TimeDay(now)); }
string GVKey(string s) { return "AT_" + IntegerToString(MagicNumber) + "_" + s + "_" + DayKey(); }
double GetStartBalance() { string k=GVKey("bal"); if(!GlobalVariableCheck(k)) GlobalVariableSet(k, AccountBalance()); return GlobalVariableGet(k); }
int GetTradesToday() { string k=GVKey("trd"); if(!GlobalVariableCheck(k)) GlobalVariableSet(k, 0); return (int)GlobalVariableGet(k); }
void IncTradesToday() { string k=GVKey("trd"); GlobalVariableSet(k, GetTradesToday()+1); }

void ApplyManagement() {
   for(int i=OrdersTotal()-1; i>=0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES) || OrderSymbol()!=Symbol() || OrderMagicNumber()!=MagicNumber) continue;
      double pip = _pip(); double profit = (OrderType()==OP_BUY)?(Bid-OrderOpenPrice())/pip:(OrderOpenPrice()-Ask)/pip;
      if(BreakEvenEnabled && profit>=BreakEvenTriggerPips) {
         double sl = OrderOpenPrice();
         if((OrderType()==OP_BUY && OrderStopLoss()<sl) || (OrderType()==OP_SELL && (OrderStopLoss()>sl || OrderStopLoss()==0)))
            OrderModify(OrderTicket(), OrderOpenPrice(), NormalizeDouble(sl, Digits), OrderTakeProfit(), 0, clrNONE);
      }
   }
}

void CloseAtCutoff() {
   if(TimeHour(TimeCurrent()) >= DayCloseHour && TimeMinute(TimeCurrent()) >= DayCloseMinute) {
      for(int i=OrdersTotal()-1; i>=0; i--) {
         if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES) && OrderSymbol()==Symbol() && OrderMagicNumber()==MagicNumber)
            OrderClose(OrderTicket(), OrderLots(), (OrderType()==OP_BUY?Bid:Ask), SlippagePoints, clrNONE);
      }
   }
}
