//+------------------------------------------------------------------+
//|                                                   DataProbe.mq5  |
//|  Evidence collector: what market data does THIS account, server  |
//|  and symbol actually deliver? Writes JSON to the terminal's      |
//|  Common\Files folder for bot/probe_classify.py.                   |
//|                                                                  |
//|  Run as a Script on any chart of a LiteFinance MT5 DEMO account. |
//|  Read-only: it places no orders.                                 |
//|  Status: written, NOT yet compiled or run (no MT5 available in   |
//|  the development environment).                                   |
//+------------------------------------------------------------------+
#property copyright "Ninja-trade-api"
#property version   "0.10"
#property script_show_inputs

input string InpSymbols      = "XAUUSD,EURUSD"; // comma separated; suffixes are auto-detected
input int    InpBookSeconds  = 120;             // how long to sample the depth of market per symbol
input int    InpBookPollMs   = 250;             // polling interval for MarketBookGet
input int    InpTickHours    = 24;              // tick statistics window
input string InpFileName     = "data_probe.json";

//--- JSON helpers --------------------------------------------------
string J(string s)
  {
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   return "\"" + s + "\"";
  }
string D(const double v, const int digits = 8) { return DoubleToString(v, digits); }
string B(const bool b) { return b ? "true" : "false"; }
string KV(const string k, const string v) { return J(k) + ":" + v; }

double Percentile(double &sorted[], const double p)
  {
   int n = ArraySize(sorted);
   if(n == 0)
      return -1.0;
   int k = (int)MathFloor(p * (n - 1));
   return sorted[k];
  }

//--- resolves "XAUUSD" to the broker's real name, e.g. "XAUUSD.ecn"
string ResolveSymbol(const string base)
  {
   if(SymbolSelect(base, true))
      return base;
   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
     {
      string name = SymbolName(i, false);
      if(StringFind(name, base) == 0 && SymbolSelect(name, true))
         return name;
     }
   return "";
  }

//--- depth of market evidence ---------------------------------------
string ProbeBook(const string sym)
  {
   bool subscribed = MarketBookAdd(sym);
   int  add_error  = subscribed ? 0 : GetLastError();
   int  snapshots = 0, non_empty = 0, max_bid = 0, max_ask = 0, max_with_vol = 0;
   double distinct[];
   int  n_distinct = 0;
   string sample = "[]";
   MqlBookInfo book[];

   ulong end_ms = GetTickCount64() + (ulong)InpBookSeconds * 1000;
   while(subscribed && GetTickCount64() < end_ms && !IsStopped())
     {
      if(MarketBookGet(sym, book))
        {
         int n = ArraySize(book);
         snapshots++;
         if(n > 0)
            non_empty++;
         int nb = 0, na = 0, nv = 0;
         for(int i = 0; i < n; i++)
           {
            if(book[i].type == BOOK_TYPE_BUY || book[i].type == BOOK_TYPE_BUY_MARKET)
               nb++;
            else
               if(book[i].type == BOOK_TYPE_SELL || book[i].type == BOOK_TYPE_SELL_MARKET)
                  na++;
            double v = (book[i].volume_real > 0.0) ? book[i].volume_real : (double)book[i].volume;
            if(v > 0.0)
              {
               nv++;
               bool seen = false;
               for(int k = 0; k < n_distinct && !seen; k++)
                  seen = (MathAbs(distinct[k] - v) < 1e-9);
               if(!seen && n_distinct < 1000)
                 {
                  ArrayResize(distinct, n_distinct + 1);
                  distinct[n_distinct++] = v;
                 }
              }
           }
         max_bid = MathMax(max_bid, nb);
         max_ask = MathMax(max_ask, na);
         max_with_vol = MathMax(max_with_vol, nv);

         if(n > 0 && sample == "[]")
           {
            sample = "[";
            int lim = MathMin(n, 20);
            for(int i = 0; i < lim; i++)
              {
               if(i > 0)
                  sample += ",";
               sample += "{" + KV("type", J(EnumToString(book[i].type))) + "," +
                         KV("price", D(book[i].price)) + "," +
                         KV("volume", IntegerToString((long)book[i].volume)) + "," +
                         KV("volume_real", D(book[i].volume_real, 4)) + "}";
              }
            sample += "]";
           }
        }
      Sleep(InpBookPollMs);
     }
   if(subscribed)
      MarketBookRelease(sym);

   return "{" + KV("subscribed", B(subscribed)) + "," +
          KV("add_error", IntegerToString(add_error)) + "," +
          KV("seconds", IntegerToString(InpBookSeconds)) + "," +
          KV("snapshots", IntegerToString(snapshots)) + "," +
          KV("non_empty_snapshots", IntegerToString(non_empty)) + "," +
          KV("max_bid_levels", IntegerToString(max_bid)) + "," +
          KV("max_ask_levels", IntegerToString(max_ask)) + "," +
          KV("levels_with_volume", IntegerToString(max_with_vol)) + "," +
          KV("distinct_volumes", IntegerToString(n_distinct)) + "," +
          KV("sample", sample) + "}";
  }

//--- tick evidence ---------------------------------------------------
int CountTicks(const string sym, const ulong from_ms, const ulong to_ms)
  {
   MqlTick t[];
   int n = CopyTicksRange(sym, t, COPY_TICKS_ALL, from_ms, to_ms);
   return n;
  }

string ProbeTicks(const string sym)
  {
   MqlTick t[];
   ulong to_ms   = (ulong)TimeCurrent() * 1000;
   ulong from_ms = to_ms - (ulong)InpTickHours * 3600 * 1000;
   int n = -1, err = 0;
   for(int attempt = 0; attempt < 5 && n <= 0; attempt++)
     {
      ResetLastError();
      n = CopyTicksRange(sym, t, COPY_TICKS_ALL, from_ms, to_ms);
      err = GetLastError();
      if(n <= 0)
         Sleep(2000); // tick history may still be synchronising
     }

   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   int with_last = 0, with_flag_vol = 0, with_real_vol = 0, with_buy_sell = 0;
   double spreads[];
   double gaps[];
   ArrayResize(spreads, MathMax(n, 0));
   ArrayResize(gaps, MathMax(n - 1, 0));
   int ns = 0, ng = 0;
   for(int i = 0; i < n; i++)
     {
      if((t[i].flags & TICK_FLAG_LAST) != 0)
         with_last++;
      if((t[i].flags & TICK_FLAG_VOLUME) != 0)
         with_flag_vol++;
      if((t[i].flags & (TICK_FLAG_BUY | TICK_FLAG_SELL)) != 0)
         with_buy_sell++;
      if(t[i].volume_real > 0.0 || t[i].volume > 0)
         with_real_vol++;
      if(t[i].bid > 0.0 && t[i].ask > 0.0 && point > 0.0)
         spreads[ns++] = (t[i].ask - t[i].bid) / point;
      if(i > 0)
         gaps[ng++] = (double)(t[i].time_msc - t[i - 1].time_msc);
     }
   ArrayResize(spreads, ns);
   ArrayResize(gaps, ng);
   ArraySort(spreads);
   ArraySort(gaps);

   //--- how far back does tick history go? (matters for backtests)
   ulong day = 86400000;
   int n30  = CountTicks(sym, to_ms - 30 * day,  to_ms - 30 * day + 3600000);
   int n180 = CountTicks(sym, to_ms - 180 * day, to_ms - 180 * day + 3600000);
   int n365 = CountTicks(sym, to_ms - 365 * day, to_ms - 365 * day + 3600000);

   return "{" + KV("hours", IntegerToString(InpTickHours)) + "," +
          KV("count", IntegerToString(n)) + "," +
          KV("copy_error", IntegerToString(n > 0 ? 0 : err)) + "," +
          KV("with_last", IntegerToString(with_last)) + "," +
          KV("with_flag_volume", IntegerToString(with_flag_vol)) + "," +
          KV("with_real_volume", IntegerToString(with_real_vol)) + "," +
          KV("with_buy_sell_flag", IntegerToString(with_buy_sell)) + "," +
          KV("spread_points_p50", D(Percentile(spreads, 0.50), 1)) + "," +
          KV("spread_points_p90", D(Percentile(spreads, 0.90), 1)) + "," +
          KV("spread_points_p99", D(Percentile(spreads, 0.99), 1)) + "," +
          KV("spread_points_max", D(ns > 0 ? spreads[ns - 1] : -1.0, 1)) + "," +
          KV("interval_ms_p50", D(Percentile(gaps, 0.50), 0)) + "," +
          KV("interval_ms_p90", D(Percentile(gaps, 0.90), 0)) + "," +
          KV("ticks_in_1h_30d_ago", IntegerToString(n30)) + "," +
          KV("ticks_in_1h_180d_ago", IntegerToString(n180)) + "," +
          KV("ticks_in_1h_365d_ago", IntegerToString(n365)) + "}";
  }

//--- commission actually charged on this account (needs past deals)
string ProbeCommission(const string sym)
  {
   double comm = 0.0, vol = 0.0;
   int deals = 0;
   if(HistorySelect(TimeCurrent() - 90 * 86400, TimeCurrent()))
     {
      int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++)
        {
         ulong tk = HistoryDealGetTicket(i);
         if(tk == 0 || HistoryDealGetString(tk, DEAL_SYMBOL) != sym)
            continue;
         deals++;
         comm += HistoryDealGetDouble(tk, DEAL_COMMISSION);
         vol  += HistoryDealGetDouble(tk, DEAL_VOLUME);
        }
     }
   return "{" + KV("deals", IntegerToString(deals)) + "," +
          KV("commission_total", D(comm, 2)) + "," +
          KV("volume_total", D(vol, 2)) + "," +
          KV("commission_per_lot_per_side", D(vol > 0 ? comm / vol : 0.0, 4)) + "}";
  }

string ProbeSymbol(const string base)
  {
   string sym = ResolveSymbol(base);
   if(sym == "")
      return "{" + KV("name", J(base)) + "," + KV("error", J("symbol not found")) + "}";

   double margin = 0.0;
   bool   has_margin = OrderCalcMargin(ORDER_TYPE_BUY, sym, 1.0, SymbolInfoDouble(sym, SYMBOL_ASK), margin);
   PrintFormat("Probing %s: sampling depth of market for %d s ...", sym, InpBookSeconds);

   string s = "{" + KV("name", J(sym)) + "," +
              KV("requested", J(base)) + "," +
              KV("path", J(SymbolInfoString(sym, SYMBOL_PATH))) + "," +
              KV("exchange", J(SymbolInfoString(sym, SYMBOL_EXCHANGE))) + "," +
              KV("trade_exemode", J(EnumToString((ENUM_SYMBOL_TRADE_EXECUTION)SymbolInfoInteger(sym, SYMBOL_TRADE_EXEMODE)))) + "," +
              KV("calc_mode", J(EnumToString((ENUM_SYMBOL_CALC_MODE)SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE)))) + "," +
              KV("chart_mode", J(EnumToString((ENUM_SYMBOL_CHART_MODE)SymbolInfoInteger(sym, SYMBOL_CHART_MODE)))) + "," +
              KV("ticks_bookdepth", IntegerToString(SymbolInfoInteger(sym, SYMBOL_TICKS_BOOKDEPTH))) + "," +
              KV("digits", IntegerToString(SymbolInfoInteger(sym, SYMBOL_DIGITS))) + "," +
              KV("point", D(SymbolInfoDouble(sym, SYMBOL_POINT))) + "," +
              KV("tick_size", D(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE))) + "," +
              KV("tick_value_loss", D(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE_LOSS))) + "," +
              KV("contract_size", D(SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE), 2)) + "," +
              KV("volume_min", D(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), 4)) + "," +
              KV("volume_step", D(SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP), 4)) + "," +
              KV("volume_max", D(SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX), 2)) + "," +
              KV("stops_level", IntegerToString(SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL))) + "," +
              KV("freeze_level", IntegerToString(SymbolInfoInteger(sym, SYMBOL_TRADE_FREEZE_LEVEL))) + "," +
              KV("spread_float", B((bool)SymbolInfoInteger(sym, SYMBOL_SPREAD_FLOAT))) + "," +
              KV("filling_mode_flags", IntegerToString(SymbolInfoInteger(sym, SYMBOL_FILLING_MODE))) + "," +
              KV("swap_long", D(SymbolInfoDouble(sym, SYMBOL_SWAP_LONG), 4)) + "," +
              KV("swap_short", D(SymbolInfoDouble(sym, SYMBOL_SWAP_SHORT), 4)) + "," +
              KV("margin_1lot_buy", has_margin ? D(margin, 2) : "null") + "," +
              KV("m1_first_date_local", IntegerToString(SeriesInfoInteger(sym, PERIOD_M1, SERIES_FIRSTDATE))) + "," +
              KV("m1_first_date_server", IntegerToString(SeriesInfoInteger(sym, PERIOD_M1, SERIES_SERVER_FIRSTDATE))) + "," +
              KV("book", ProbeBook(sym)) + "," +
              KV("ticks", ProbeTicks(sym)) + "," +
              KV("commission", ProbeCommission(sym)) + "}";
   return s;
  }

void OnStart()
  {
   string parts[];
   int n = StringSplit(InpSymbols, ',', parts);

   string acc = "{" + KV("server", J(AccountInfoString(ACCOUNT_SERVER))) + "," +
                KV("company", J(AccountInfoString(ACCOUNT_COMPANY))) + "," +
                KV("trade_mode", J(EnumToString((ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)))) + "," +
                KV("margin_mode", J(EnumToString((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)))) + "," +
                KV("currency", J(AccountInfoString(ACCOUNT_CURRENCY))) + "," +
                KV("leverage", IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE))) + "," +
                KV("terminal_build", IntegerToString(TerminalInfoInteger(TERMINAL_BUILD))) + "," +
                KV("ping_last_us", IntegerToString(TerminalInfoInteger(TERMINAL_PING_LAST))) + "," +
                KV("server_time", J(TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS))) + "," +
                KV("gmt_time", J(TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS))) + "}";

   string syms = "[";
   for(int i = 0; i < n && !IsStopped(); i++)
     {
      string base = parts[i];
      StringTrimLeft(base);
      StringTrimRight(base);
      if(base == "")
         continue;
      if(syms != "[")
         syms += ",";
      syms += ProbeSymbol(base);
     }
   syms += "]";

   string json = "{" + KV("probe_version", J("0.10")) + "," + KV("account", acc) + "," + KV("symbols", syms) + "}";

   int h = FileOpen(InpFileName, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h == INVALID_HANDLE)
     {
      PrintFormat("Cannot write %s: error %d", InpFileName, GetLastError());
      return;
     }
   FileWriteString(h, json);
   FileClose(h);
   PrintFormat("Probe written to %s\\Files\\%s", TerminalInfoString(TERMINAL_COMMONDATA_PATH), InpFileName);
  }
//+------------------------------------------------------------------+
