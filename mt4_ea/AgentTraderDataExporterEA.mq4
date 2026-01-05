#property copyright "Copyright 2026, Ezekiel98Tz"
#property link      "https://github.com/Ezekiel98Tz/Agent_trader"
#property version   "1.00"
#property strict

//--- Input Parameters
input int      UpdateIntervalSeconds = 60;   // Seconds between exports
input int      H4_Bars               = 500;  // Bars to export for H4
input int      H1_Bars               = 800;  // Bars to export for H1
input int      M15_Bars              = 1500; // Bars to export for M15

//--- Global Variables
string OutSubdir = "agent_trader\\data";
datetime last_update = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("AgentTrader Data Exporter Started. Target: ", Symbol());
   // Create directory in Common\Files by writing a dummy file
   int h = FileOpen(OutSubdir + "\\init.txt", FILE_WRITE|FILE_TXT|FILE_COMMON);
   if(h != INVALID_HANDLE) FileClose(h);
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   if(TimeCurrent() - last_update < UpdateIntervalSeconds)
      return;
      
   bool ok = true;
   ok &= _export_tf(Symbol(), PERIOD_H4, H4_Bars);
   ok &= _export_tf(Symbol(), PERIOD_H1, H1_Bars);
   ok &= _export_tf(Symbol(), PERIOD_M15, M15_Bars);
   
   if(ok) {
      last_update = TimeCurrent();
      Print("Data exported successfully at ", TimeToStr(last_update));
   }
}

//+------------------------------------------------------------------+
//| Export logic                                                     |
//+------------------------------------------------------------------+
bool _export_tf(string sym, int tf, int count)
{
   string tf_name = _get_tf_name(tf);
   string filename = OutSubdir + "\\" + sym + "_" + tf_name + ".csv";
   
   int handle = FileOpen(filename, FILE_WRITE|FILE_CSV|FILE_COMMON, ',');
   if(handle == INVALID_HANDLE) {
      Print("Error opening file for write: ", filename, " Error: ", GetLastError());
      return false;
   }
   
   // Write Header
   FileWrite(handle, "time", "open", "high", "low", "close", "tick_volume");
   
   // Export from oldest to newest for pandas compatibility
   for(int i = count - 1; i >= 0; i--)
   {
      datetime t = iTime(sym, tf, i);
      double o   = iOpen(sym, tf, i);
      double h   = iHigh(sym, tf, i);
      double l   = iLow(sym, tf, i);
      double c   = iClose(sym, tf, i);
      long v     = iVolume(sym, tf, i);
      
      FileWrite(handle, 
         TimeToStr(t, TIME_DATE|TIME_MINUTES|TIME_SECONDS),
         DoubleToStr(o, Digits),
         DoubleToStr(h, Digits),
         DoubleToStr(l, Digits),
         DoubleToStr(c, Digits),
         IntegerToString(v)
      );
   }
   
   FileClose(handle);
   return true;
}

string _get_tf_name(int tf)
{
   switch(tf) {
      case PERIOD_M15: return "M15";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      default: return "UNK";
   }
}
