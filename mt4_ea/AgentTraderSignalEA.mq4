#property strict

extern bool AutoTrade = false;
extern bool VisualOnly = true;
extern string InboxSubdir = "agent_trader\\inbox";
extern double Lots = 0.10;
extern int SlippagePoints = 20;
extern int MagicNumber = 240102;
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
      if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
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
      int ticket = OrderSend(Symbol(), cmd, lots, price, SlippagePoints, sl, tp, "AgentTrader", MagicNumber, 0, clrNONE);
      if(ticket < 0)
         Print("OrderSend failed: ", GetLastError());
   }

   MarkSignalConsumed(filename);
   return 0;
}

