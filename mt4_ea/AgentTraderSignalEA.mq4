#property strict

extern bool AutoTrade = false;
extern bool VisualOnly = true;
extern string InboxSubdir = "agent_trader\\inbox";
extern double Lots = 0.10;
extern int SlippagePoints = 20;
extern int MagicNumber = 240102;
extern bool BlockIfAnyOpenPosition = false;
extern int MaxTradesPerDay = 3;
extern double MaxDailyLossMoney = 50.0;
extern double MaxSpreadPips = 2.5;
extern bool BreakEvenEnabled = true;
extern double BreakEvenTriggerPips = 10.0;
extern bool TrailingEnabled = false;
extern double TrailingPips = 12.0;
extern int DayCloseHour = 21;
extern int DayCloseMinute = 30;

string g_last_signal_id = "";

double PipValue()
{
   string s = Symbol();
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
   datetime now = TimeCurrent();
   int y = TimeYear(now);
   int m = TimeMonth(now);
   int d = TimeDay(now);
   return IntegerToString(y) + StringFormat("%02d", m) + StringFormat("%02d", d);
}

string GVKey(const string suffix)
{
   return "AgentTrader_" + IntegerToString(MagicNumber) + "_" + suffix + "_" + DayKey();
}

double GetStartBalance()
{
   string key = GVKey("start_balance");
   if(!GlobalVariableCheck(key))
   {
      double b = AccountBalance();
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
   double pip = PipValue();
   if(pip <= 0.0)
      return 9999.0;
   return (Ask - Bid) / pip;
}

bool StopsValid(const bool buy, const double sl, const double tp)
{
   int stop_level = (int)MarketInfo(Symbol(), MODE_STOPLEVEL);
   double min_dist = (double)stop_level * Point;
   double price = buy ? Ask : Bid;
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

bool ReadNextSignal(string &id, datetime &t_utc, string &symbol, string &side, double &entry, double &sl, double &tp, double &confluence, double &prob, string &session_state, string &regime, string &quality, double &risk_mult, string &mode, string &filename_out)
{
   string subdir = InboxSubdir;
   int handle = FileFindFirst(subdir + "\\signal_*.csv", filename_out, FILE_COMMON);
   if(handle == INVALID_HANDLE)
      return false;

   bool found = false;
   while(true)
   {
      if(filename_out == "" || FileIsExist(subdir + "\\" + filename_out, FILE_COMMON) == false)
      {
         if(!FileFindNext(handle, filename_out))
            break;
         continue;
      }

      int fh = FileOpen(subdir + "\\" + filename_out, FILE_READ|FILE_COMMON|FILE_ANSI);
      if(fh == INVALID_HANDLE)
      {
         if(!FileFindNext(handle, filename_out))
            break;
         continue;
      }

      string line = FileReadString(fh);
      FileClose(fh);

      string parts[];
      int n = StringSplit(line, ',', parts);
      if(n < 14)
      {
         if(!FileFindNext(handle, filename_out))
            break;
         continue;
      }

      id = parts[0];
      t_utc = StringToTime(parts[1]);
      symbol = parts[2];
      side = parts[3];
      entry = StrToDouble(parts[4]);
      sl = StrToDouble(parts[5]);
      tp = StrToDouble(parts[6]);
      confluence = StrToDouble(parts[7]);
      prob = StrToDouble(parts[8]);
      session_state = parts[9];
      regime = parts[10];
      quality = parts[11];
      risk_mult = StrToDouble(parts[12]);
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
   for(int i=OrdersTotal()-1; i>=0; --i)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() != Symbol())
         continue;
      if(BlockIfAnyOpenPosition)
         return true;
      if(OrderMagicNumber() == MagicNumber)
         return true;
   }
   return false;
}

void ApplyManagement()
{
   for(int i=OrdersTotal()-1; i>=0; --i)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber)
         continue;

      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL)
         continue;

      double entry = OrderOpenPrice();
      double sl = OrderStopLoss();
      double tp = OrderTakeProfit();
      double pip = PipValue();
      double price = (type == OP_BUY) ? Bid : Ask;
      double profit_pips = (type == OP_BUY) ? (price - entry)/pip : (entry - price)/pip;

      bool need_modify = false;
      double new_sl = sl;

      if(BreakEvenEnabled && profit_pips >= BreakEvenTriggerPips)
      {
         if(type == OP_BUY && (sl < entry || sl == 0.0))
         {
            new_sl = entry;
            need_modify = true;
         }
         if(type == OP_SELL && (sl > entry || sl == 0.0))
         {
            new_sl = entry;
            need_modify = true;
         }
      }

      if(TrailingEnabled && profit_pips > TrailingPips)
      {
         if(type == OP_BUY)
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
         bool ok = OrderModify(OrderTicket(), OrderOpenPrice(), NormalizeDouble(new_sl, Digits), tp, 0, clrNONE);
         if(!ok)
            Print("OrderModify failed: ", GetLastError());
      }
   }
}

void CloseAtCutoff()
{
   datetime now = TimeCurrent();
   int h = TimeHour(now);
   int m = TimeMinute(now);
   if(h < DayCloseHour || (h == DayCloseHour && m <= DayCloseMinute))
      return;

   for(int i=OrdersTotal()-1; i>=0; --i)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber)
         continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL)
         continue;
      double price = (type == OP_BUY) ? Bid : Ask;
      bool ok = OrderClose(OrderTicket(), OrderLots(), price, SlippagePoints, clrNONE);
      if(!ok)
         Print("OrderClose failed: ", GetLastError());
   }
}

int start()
{
   ApplyManagement();
   CloseAtCutoff();

   string id, symbol, side, session_state, regime, quality, mode, filename;
   datetime t_utc;
   double entry, sl, tp, confluence, prob, risk_mult;

   if(!ReadNextSignal(id, t_utc, symbol, side, entry, sl, tp, confluence, prob, session_state, regime, quality, risk_mult, mode, filename))
      return 0;

   if(id == g_last_signal_id)
   {
      MarkSignalConsumed(filename);
      return 0;
   }
   g_last_signal_id = id;

   if(symbol != Symbol())
   {
      MarkSignalConsumed(filename);
      return 0;
   }

   if(HasOpenPosition())
   {
      MarkSignalConsumed(filename);
      return 0;
   }

   bool do_trade = AutoTrade && !VisualOnly && (mode == "live" || mode == "paper");
   if(VisualOnly || mode == "visual")
      do_trade = false;

   Print("AgentTrader signal: session=", session_state, " regime=", regime, " prob=", DoubleToString(prob, 4), " confluence=", DoubleToString(confluence, 2), " quality=", quality, " risk_mult=", DoubleToString(risk_mult, 2), " mode=", mode);

   if(quality == "SKIP" || risk_mult <= 0.0)
      do_trade = false;

   int trades_today = GetTradesToday();
   double start_balance = GetStartBalance();
   double daily_pnl = AccountBalance() - start_balance;
   double spread_pips = CurrentSpreadPips();
   if(trades_today >= MaxTradesPerDay)
      do_trade = false;
   if(MaxDailyLossMoney > 0.0 && daily_pnl <= -MaxDailyLossMoney)
      do_trade = false;
   if(MaxSpreadPips > 0.0 && spread_pips > MaxSpreadPips)
      do_trade = false;

   if(do_trade)
   {
      double lots = Lots * risk_mult;
      if(lots <= 0.0)
      {
         MarkSignalConsumed(filename);
         return 0;
      }

      int cmd = (side == "buy") ? OP_BUY : OP_SELL;
      double price = (cmd == OP_BUY) ? Ask : Bid;
      double sl_n = NormalizeDouble(sl, Digits);
      double tp_n = NormalizeDouble(tp, Digits);
      if(StopsValid(cmd == OP_BUY, sl_n, tp_n))
      {
         int ticket = OrderSend(Symbol(), cmd, lots, price, SlippagePoints, sl_n, tp_n, "AgentTrader", MagicNumber, 0, clrNONE);
         if(ticket < 0)
            Print("OrderSend failed: ", GetLastError());
         else
            IncTradesToday();
      }
   }

   MarkSignalConsumed(filename);
   return 0;
}
