#property strict

input bool AutoTrade = false;
input bool VisualOnly = true;
input string InboxSubdir = "agent_trader\\inbox";
input double Lots = 0.10;
input int SlippagePoints = 20;
input long MagicNumber = 240102;
input bool BlockIfAnyOpenPosition = false;
input int MaxTradesPerDay = 3;
input double MaxDailyLossMoney = 50.0;
input double MaxSpreadPips = 2.5;
input bool BreakEvenEnabled = true;
input double BreakEvenTriggerPips = 10.0;
input bool TrailingEnabled = false;
input double TrailingPips = 12.0;
input int DayCloseHour = 21;
input int DayCloseMinute = 30;

string g_last_signal_id = "";

double PipValue()
{
   string s = _Symbol;
   int n = StringLen(s);
   if(n >= 3 && StringSubstr(s, n-3, 3) == "JPY")
      return 0.01;
   return 0.0001;
}

double PipsToPrice(double pips)
{
   return pips * PipValue();
}

string DayKey()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   return IntegerToString(dt.year) + StringFormat("%02d", dt.mon) + StringFormat("%02d", dt.day);
}

string GVKey(const string suffix)
{
   return "AgentTrader_" + IntegerToString((int)MagicNumber) + "_" + suffix + "_" + DayKey();
}

double GetStartBalance()
{
   string key = GVKey("start_balance");
   if(!GlobalVariableCheck(key))
   {
      double b = AccountInfoDouble(ACCOUNT_BALANCE);
      GlobalVariableSet(key, b);
      return b;
   }
   return GlobalVariableGet(key);
}

int GetTradesToday()
{
   string key = GVKey("trades");
   if(!GlobalVariableCheck(key))
   {
      GlobalVariableSet(key, 0.0);
      return 0;
   }
   return (int)GlobalVariableGet(key);
}

void IncTradesToday()
{
   string key = GVKey("trades");
   int n = GetTradesToday();
   GlobalVariableSet(key, (double)(n + 1));
}

double CurrentSpreadPips()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double pip = PipValue();
   if(pip <= 0.0)
      return 9999.0;
   return (ask - bid) / pip;
}

bool StopsValid(const bool buy, const double sl, const double tp)
{
   int stops_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double min_dist = (double)stops_level * _Point;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double price = buy ? ask : bid;
   if(min_dist <= 0.0)
      return true;
   if(buy)
   {
      if(sl >= price || tp <= price)
         return false;
      if((price - sl) < min_dist || (tp - price) < min_dist)
         return false;
   }
   else
   {
      if(sl <= price || tp >= price)
         return false;
      if((sl - price) < min_dist || (price - tp) < min_dist)
         return false;
   }
   return true;
}

bool ReadNextSignal(string &id, datetime &t_utc, string &symbol, string &side, double &entry, double &sl, double &tp, double &confluence, double &prob, string &session_state, string &regime, string &quality, double &risk_mult, string &mode, string &path_out)
{
   string subdir = InboxSubdir;
   int handle = FileFindFirst(subdir + "\\signal_*.csv", path_out, FILE_COMMON);
   if(handle == INVALID_HANDLE)
      return false;

   bool found = false;
   while(true)
   {
      if(path_out == "" || FileIsExist(subdir + "\\" + path_out, FILE_COMMON) == false)
      {
         if(!FileFindNext(handle, path_out))
            break;
         continue;
      }

      int fh = FileOpen(subdir + "\\" + path_out, FILE_READ|FILE_COMMON|FILE_ANSI);
      if(fh == INVALID_HANDLE)
      {
         if(!FileFindNext(handle, path_out))
            break;
         continue;
      }

      string line = FileReadString(fh);
      FileClose(fh);

      string parts[];
      int n = StringSplit(line, ',', parts);
      if(n < 14)
      {
         if(!FileFindNext(handle, path_out))
            break;
         continue;
      }

      id = parts[0];
      t_utc = StringToTime(parts[1]);
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
      found = true;
      break;
   }

   FileFindClose(handle);
   return found;
}

void MarkSignalConsumed(const string filename)
{
   string subdir = InboxSubdir;
   string src = subdir + "\\" + filename;
   string dst = subdir + "\\consumed_" + filename;
   if(FileIsExist(src, FILE_COMMON))
      FileMove(src, dst, FILE_COMMON);
}

bool HasOpenPosition()
{
   for(int i=PositionsTotal()-1; i>=0; --i)
   {
      if(PositionSelectByIndex(i))
      {
         string sym = PositionGetString(POSITION_SYMBOL);
         if(sym != _Symbol)
            continue;
         if(BlockIfAnyOpenPosition)
            return true;
         long mg = PositionGetInteger(POSITION_MAGIC);
         if(mg == MagicNumber)
            return true;
      }
   }
   return false;
}

void ApplyManagement()
{
   if(!PositionSelect(_Symbol))
      return;

   long type = PositionGetInteger(POSITION_TYPE);
   double entry = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl = PositionGetDouble(POSITION_SL);
   double tp = PositionGetDouble(POSITION_TP);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double price = (type == POSITION_TYPE_BUY) ? bid : ask;

   double pip = PipValue();
   double profit_pips = (type == POSITION_TYPE_BUY) ? (price - entry)/pip : (entry - price)/pip;

   MqlTradeRequest req;
   MqlTradeResult res;
   ZeroMemory(req);
   ZeroMemory(res);

   bool need_modify = false;
   double new_sl = sl;

   if(BreakEvenEnabled && profit_pips >= BreakEvenTriggerPips)
   {
      if(type == POSITION_TYPE_BUY && (sl < entry || sl == 0.0))
      {
         new_sl = entry;
         need_modify = true;
      }
      if(type == POSITION_TYPE_SELL && (sl > entry || sl == 0.0))
      {
         new_sl = entry;
         need_modify = true;
      }
   }

   if(TrailingEnabled && profit_pips > TrailingPips)
   {
      if(type == POSITION_TYPE_BUY)
      {
         double trail = price - PipsToPrice(TrailingPips);
         if(trail > new_sl)
         {
            new_sl = trail;
            need_modify = true;
         }
      }
      else
      {
         double trail = price + PipsToPrice(TrailingPips);
         if(trail < new_sl || new_sl == 0.0)
         {
            new_sl = trail;
            need_modify = true;
         }
      }
   }

   if(need_modify)
   {
      req.action = TRADE_ACTION_SLTP;
      req.symbol = _Symbol;
      req.sl = NormalizeDouble(new_sl, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
      req.tp = tp;
      OrderSend(req, res);
   }
}

void CloseAtCutoff()
{
   datetime now = TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(now, dt);
   if(dt.hour < DayCloseHour || (dt.hour == DayCloseHour && dt.min <= DayCloseMinute))
      return;

   if(!PositionSelect(_Symbol))
      return;

   long type = PositionGetInteger(POSITION_TYPE);
   double volume = PositionGetDouble(POSITION_VOLUME);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   MqlTradeRequest req;
   MqlTradeResult res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = _Symbol;
   req.volume = volume;
   req.type = (type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.price = (type == POSITION_TYPE_BUY) ? bid : ask;
   req.deviation = SlippagePoints;
   req.type_filling = ORDER_FILLING_FOK;
   OrderSend(req, res);
}

int OnInit()
{
   return(INIT_SUCCEEDED);
}

void OnTick()
{
   ApplyManagement();
   CloseAtCutoff();

   string id, symbol, side, session_state, regime, quality, mode, filename;
   datetime t_utc;
   double entry, sl, tp, confluence, prob, risk_mult;

   if(!ReadNextSignal(id, t_utc, symbol, side, entry, sl, tp, confluence, prob, session_state, regime, quality, risk_mult, mode, filename))
      return;

   if(id == g_last_signal_id)
   {
      MarkSignalConsumed(filename);
      return;
   }

   g_last_signal_id = id;

   if(symbol != _Symbol)
   {
      MarkSignalConsumed(filename);
      return;
   }

   if(HasOpenPosition())
   {
      MarkSignalConsumed(filename);
      return;
   }

   bool do_trade = AutoTrade && !VisualOnly && (mode == "live" || mode == "paper");
   if(VisualOnly || mode == "visual")
      do_trade = false;

   Print("AgentTrader signal: session=", session_state, " regime=", regime, " prob=", DoubleToString(prob, 4), " confluence=", DoubleToString(confluence, 2), " quality=", quality, " risk_mult=", DoubleToString(risk_mult, 2), " mode=", mode);

   if(quality == "SKIP" || risk_mult <= 0.0)
      do_trade = false;

   int trades_today = GetTradesToday();
   double start_balance = GetStartBalance();
   double daily_pnl = AccountInfoDouble(ACCOUNT_BALANCE) - start_balance;
   double spread_pips = CurrentSpreadPips();
   if(trades_today >= MaxTradesPerDay)
      do_trade = false;
   if(MaxDailyLossMoney > 0.0 && daily_pnl <= -MaxDailyLossMoney)
      do_trade = false;
   if(MaxSpreadPips > 0.0 && spread_pips > MaxSpreadPips)
      do_trade = false;

   if(do_trade)
   {
      MqlTradeRequest req;
      MqlTradeResult res;
      ZeroMemory(req);
      ZeroMemory(res);
      req.action = TRADE_ACTION_DEAL;
      req.symbol = _Symbol;
      req.volume = Lots * risk_mult;
      req.deviation = SlippagePoints;
      req.magic = MagicNumber;
      req.type_filling = (ENUM_ORDER_TYPE_FILLING)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);

      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      bool buy = (side == "buy");
      req.type = buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      req.price = buy ? ask : bid;
      int digs = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      double sl_n = NormalizeDouble(sl, digs);
      double tp_n = NormalizeDouble(tp, digs);
      if(!StopsValid(buy, sl_n, tp_n))
      {
         do_trade = false;
      }
      else
      {
         req.sl = sl_n;
         req.tp = tp_n;
         if(OrderSend(req, res))
         {
            if(res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_PLACED)
               IncTradesToday();
         }
         else
         {
            Print("OrderSend failed: retcode=", (int)res.retcode);
         }
      }
   }

   MarkSignalConsumed(filename);
}
