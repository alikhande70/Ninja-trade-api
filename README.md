# Ninja-trade-api

Research and build of an automated trading bot driven by live Level 2 (order book) data, with an AI model in a supervisory role.

## Documents
- [docs/01-feasibility-report.md](docs/01-feasibility-report.md): feasibility study, option comparison, cost estimate and phased roadmap (Persian)
- [docs/02-autonomous-bot-design.md](docs/02-autonomous-bot-design.md): revised plan for a 24/7 autonomous bot on a $500 total budget (Persian)
- [docs/04-l2-impact-and-evidence.md](docs/04-l2-impact-and-evidence.md): **latest**: what is lost without L2, evidence so far, options, work status (Persian)
- [docs/03-mt5-litefinance-design.md](docs/03-mt5-litefinance-design.md): MT5 plan: autonomous MT5 Expert Advisor on LiteFinance with balance-based sizing, provider-agnostic LLM supervisor, full cost estimate (Persian)
- [docs/site/index.html](docs/site/index.html): web version of the plan (Persian, RTL)

## Code
- `bot/sizing.py`: balance-based lot sizing and loss guards (reference implementation)
- `bot/orderbook.py`: venue-independent L2 book, OFI, microprice, imbalance
- `bot/probe_classify.py`: classifies what market data an MT5 account really provides
- `mt5/`: MQL5 data probe, sizing port and self-test (not yet compiled; see `mt5/README.md`)
- Tests: `python3 -m unittest discover -s tests -t .`

## Ground rules
- All development and testing runs on simulated/paper accounts.
- No subscriptions, financial commitments or live-money trading without explicit owner approval.
