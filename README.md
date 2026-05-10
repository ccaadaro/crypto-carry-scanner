# Crypto Carry and Basis Scanner

[![Institutional Grade](https://img.shields.io/badge/Institutional-Grade-blue.svg)](https://github.com/ccaadaro/crypto-carry-scanner)
[![Market Neutral](https://img.shields.io/badge/Strategy-Market--Neutral-green.svg)](https://github.com/ccaadaro/crypto-carry-scanner)
[![Research Only](https://img.shields.io/badge/Status-Research--Only-yellow.svg)](https://github.com/ccaadaro/crypto-carry-scanner)

An institutional-grade research tool designed to identify, quantify, and audit crypto carry and basis opportunities. This scanner focuses on spot vs. perpetual basis, funding rate arbitrage, and synthetic stress testing to ensure strategy robustness.

## Overview

The **Crypto Carry Scanner** is a read-only market-neutral tool built to provide deep visibility into the basis and funding landscape. It decomposes historical trade performance into granular PnL drivers and validates strategy viability through capital occupancy metrics and liquidation distance modeling.

### Core Objectives
- **Identify Opportunities**: Detect explicit spread/carry opportunities (Spot vs. Perp basis).
- **Risk Audit**: Conduct forensic accounting and risk consistency audits.
- **Stress Testing**: Model basis widening and liquidation risks across varying leverage profiles.
- **Monotonicity Validation**: Ensure risk metrics (liquidation counts) scale logically with shock size and leverage.

## Key Metrics
The scanner tracks and reports:
- **Basis (bps/Annualized)**: (Perp Mark - Spot) / Spot.
- **Funding Carry**: Net expected carry after fees, slippage, and borrow costs.
- **Liquidation Buffer**: Distance to liquidation under synthetic price shocks.
- **Opportunity Score**: A multi-factor ranking of current market opportunities.

## Project Structure
- [CARRY_PROTOCOL.md](CARRY_PROTOCOL.md): Detailed research protocol, success gates, and kill criteria.
- `scripts/`:
    - `live_carry_scanner.py`: Real-time market scanning and opportunity detection.
    - `run_risk_engine.py`: Unified risk engine for historical and synthetic stress testing.
    - `evaluate_carry_opportunities.py`: Granular PnL decomposition and performance auditing.
    - `audit_carry_results.py`: forensic consistency checks and report generation.
- `cache/`: Local data caching for high-performance analysis.
- `reports/`: Granular CSV and JSON reports documenting scan results and risk audits.

## Usage
The scanner is designed as a standalone research suite.
```bash
# Run the live scanner
python scripts/live_carry_scanner.py

# Execute the risk engine with synthetic shocks
python scripts/run_risk_engine.py --shocks 100 200 500

# Perform a forensic audit of carry opportunities
python scripts/audit_carry_results.py
```

## Risk Model & Assumptions
- **Unified Liquidation Model**: Uses `compute_margin_state` as the single source of truth for all risk calculations.
- **Conservative Costs**: Default assumptions include 10bps spot fees, 5bps perp fees, and 2-5bps slippage per leg.
- **Kill Criteria**: Automatically flags or blocks research if data timestamps are non-causal or expected carry disappears after costs.

## Disclaimer
**RESEARCH ONLY.** This software is provided for educational and research purposes. It does not contain execution logic. Trading cryptocurrencies involves significant risk of loss. The authors are not responsible for any financial losses incurred.

---
*Developed by Senior Quantitative Research Engineer / Institutional Research Auditor*
