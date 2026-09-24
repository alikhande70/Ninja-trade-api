//+------------------------------------------------------------------+
//|                                              SizingSelfTest.mq5  |
//|  Replays tests/vectors/sizing_vectors.csv through RiskSizing.mqh |
//|  and reports every row where MQL5 differs from the Python        |
//|  reference. Copy the CSV into the terminal's Common\Files folder. |
//|  Status: written, NOT yet compiled or run.                        |
//+------------------------------------------------------------------+
#property copyright "Ninja-trade-api"
#property version   "0.10"
#property script_show_inputs

#include <RiskSizing.mqh>   // copy mt5/Include/RiskSizing.mqh to MQL5\Include

input string InpVectors = "sizing_vectors.csv";

void OnStart()
  {
   int h = FileOpen(InpVectors, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(h == INVALID_HANDLE)
     {
      PrintFormat("Cannot open Common\\Files\\%s (error %d)", InpVectors, GetLastError());
      return;
     }
   //--- skip header (15 columns)
   for(int c = 0; c < 15 && !FileIsEnding(h); c++)
      FileReadString(h);

   int total = 0, failed = 0;
   while(!FileIsEnding(h) && !IsStopped())
     {
      string name = FileReadString(h);
      if(name == "")
         break;
      double balance = StringToDouble(FileReadString(h));
      double equity  = StringToDouble(FileReadString(h));
      double risk    = StringToDouble(FileReadString(h));
      double sl      = StringToDouble(FileReadString(h));
      double ai      = StringToDouble(FileReadString(h));
      double dd      = StringToDouble(FileReadString(h));
      RsSpec spec;
      spec.tick_size       = StringToDouble(FileReadString(h));
      spec.tick_value_loss = StringToDouble(FileReadString(h));
      spec.volume_min      = StringToDouble(FileReadString(h));
      spec.volume_step     = StringToDouble(FileReadString(h));
      spec.volume_max      = StringToDouble(FileReadString(h));
      spec.commission_rt   = StringToDouble(FileReadString(h));
      double expected_lots = StringToDouble(FileReadString(h));
      string expected_reason = FileReadString(h);

      RsResult r;
      RsComputeLots(balance, equity, risk, sl, spec, r, ai, dd);
      total++;
      bool pass = (r.reason == expected_reason) && (MathAbs(r.lots - expected_lots) < 1e-8);
      if(!pass)
        {
         failed++;
         PrintFormat("FAIL %s: got lots=%.2f reason=%s, expected lots=%.2f reason=%s",
                     name, r.lots, r.reason, expected_lots, expected_reason);
        }
     }
   FileClose(h);
   PrintFormat("SizingSelfTest: %d cases, %d failed", total, failed);
  }
//+------------------------------------------------------------------+
