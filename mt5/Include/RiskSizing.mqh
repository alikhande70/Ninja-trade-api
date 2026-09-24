//+------------------------------------------------------------------+
//|                                                  RiskSizing.mqh  |
//|  MQL5 port of bot/sizing.py. Behaviour must match the Python     |
//|  reference row by row (tests/vectors/sizing_vectors.csv, checked  |
//|  in MetaTrader by Scripts/SizingSelfTest.mq5).                    |
//|  Status: written, NOT yet compiled.                               |
//+------------------------------------------------------------------+
#define RS_EPS 1e-9

struct RsSpec
  {
   double            tick_size;
   double            tick_value_loss;
   double            volume_min;
   double            volume_step;
   double            volume_max;
   double            commission_rt;   // round-turn commission per 1.0 lot
  };

struct RsResult
  {
   bool              ok;
   double            lots;
   double            base;
   double            risk_budget;
   double            actual_risk;
   double            loss_per_lot;
   string            reason;
  };

//--- reads the broker's live specification for a symbol
bool RsLoadSpec(const string sym, const double commission_rt, RsSpec &spec)
  {
   spec.tick_size       = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   spec.tick_value_loss = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE_LOSS);
   spec.volume_min      = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   spec.volume_step     = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   spec.volume_max      = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   spec.commission_rt   = commission_rt;
   return (spec.tick_size > 0.0 && spec.tick_value_loss > 0.0 && spec.volume_step > 0.0);
  }

long RsStepsDown(const double value, const double step)
  {
   return (long)MathFloor(value / step + RS_EPS);
  }

int RsStepDigits(const double step)
  {
   int d = 0;
   double s = step;
   while(d < 8 && MathAbs(s - MathRound(s)) > RS_EPS)
     {
      s *= 10.0;
      d++;
     }
   return d;
  }

double RsDrawdownThrottle(const double equity, const double peak_equity)
  {
   if(peak_equity <= 0.0)
      return 0.0;
   double dd = 1.0 - equity / peak_equity + RS_EPS;
   if(dd >= 0.20)
      return 0.0;
   if(dd >= 0.15)
      return 0.25;
   if(dd >= 0.10)
      return 0.5;
   return 1.0;
  }

void RsReject(RsResult &r, const string reason)
  {
   r.ok = false;
   r.lots = 0.0;
   r.actual_risk = 0.0;
   r.reason = reason;
  }

//--- result is returned through r; returns r.ok. margin_per_lot <= 0 disables the margin cap
bool RsComputeLots(const double balance, const double equity, const double risk_pct,
                   const double sl_distance, const RsSpec &spec, RsResult &r,
                   const double ai_multiplier = 1.0, const double dd_multiplier = 1.0,
                   const double free_margin = 0.0, const double margin_per_lot = 0.0,
                   const double max_margin_fraction = 0.30)
  {
   r.base = MathMin(balance, equity);
   r.risk_budget = 0.0;
   r.loss_per_lot = 0.0;

   if(r.base <= 0.0)                { RsReject(r, "no_funds"); return false; }
   if(sl_distance <= 0.0)           { RsReject(r, "invalid_stop"); return false; }
   if(spec.tick_size <= 0.0 || spec.tick_value_loss <= 0.0 || spec.volume_step <= 0.0)
                                    { RsReject(r, "invalid_symbol_spec"); return false; }
   if(risk_pct <= 0.0 || risk_pct > 5.0)
                                    { RsReject(r, "invalid_risk_pct"); return false; }

   double ai = MathMin(MathMax(ai_multiplier, 0.0), 1.0);
   double dd = MathMin(MathMax(dd_multiplier, 0.0), 1.0);
   r.risk_budget  = r.base * risk_pct / 100.0 * ai * dd;
   r.loss_per_lot = (sl_distance / spec.tick_size) * spec.tick_value_loss + spec.commission_rt;
   if(ai == 0.0)                    { RsReject(r, "ai_blocked"); return false; }
   if(dd == 0.0)                    { RsReject(r, "drawdown_halt"); return false; }

   long steps = RsStepsDown(r.risk_budget / r.loss_per_lot, spec.volume_step);
   steps = MathMin(steps, RsStepsDown(spec.volume_max, spec.volume_step));

   if(margin_per_lot > 0.0)
     {
      long by_margin = RsStepsDown(free_margin * max_margin_fraction / margin_per_lot, spec.volume_step);
      if(by_margin < steps)
        {
         steps = by_margin;
         if(steps * spec.volume_step + RS_EPS < spec.volume_min)
           { RsReject(r, "insufficient_margin"); return false; }
        }
     }

   double lots = NormalizeDouble(steps * spec.volume_step, RsStepDigits(spec.volume_step));
   if(lots + RS_EPS < spec.volume_min)
     { RsReject(r, "below_min_volume"); return false; }

   r.ok = true;
   r.lots = lots;
   r.actual_risk = lots * r.loss_per_lot;
   r.reason = "ok";
   return true;
  }
//+------------------------------------------------------------------+
