# CRYPTO CARRY AND BASIS SCANNER PROTOCOL

**Version**: 1.0
**Project Lead**: Senior Quantitative Research Engineer / Institutional Research Auditor

## 1. Objective
Build a read-only market-neutral crypto carry and basis scanner. The goal is to identify explicit spread/carry opportunities such as spot vs perpetual basis, funding rate carry, and future cash-and-carry opportunities.

## 2. Instruments, Initial Scope
- BTC/USDT spot
- BTCUSDT perpetual
- ETH/USDT spot
- ETHUSDT perpetual

**Later optional expansion**:
- SOL, BNB, XRP, and other top liquid assets (liquidity permitting).

## 3. Required Data
For each asset, the scanner must track:
- **Spot**: Close or mid price.
- **Perpetual**: Mark price, Index price.
- **Funding**: Funding rate, current funding timestamp, next funding timestamp.
- **Market Structure**: Volume / quote volume, bid/ask spread (or proxy).
- **Costs/Assumptions**: Fees, estimated slippage, margin assumptions.

## 4. Core Metrics
- `spot_price`
- `perp_mark_price`
- `index_price` (if available)
- `basis` = (perp_mark - spot_price) / spot_price
- `basis_bps`
- `basis_annualized`
- `funding_rate`
- `funding_annualized`
- `expected_funding_next`
- `net_expected_carry` (after fees and slippage)
- `estimated_roundtrip_cost`
- `liquidity_score`
- `spread_bps` (if available)
- `liquidation_buffer_proxy`
- `opportunity_score`

## 5. Initial Strategy Templates

### A. Positive Funding Carry (Cash-and-Carry)
- **Position**: Long spot, short perpetual.
- **Goal**: Earn positive funding if shorts receive funding.
- **Constraint**: Must account for basis movement and fees.

### B. Negative Funding Carry (Inverse Cash-and-Carry)
- **Position**: Short spot (or margin), long perpetual.
- **Status**: **DISABLED** initially. Only theoretical unless borrow cost and shorting ability are realistic.

### C. Basis Convergence
- **Position**: Long cheap leg, short expensive leg.
- **Status**: Scanner only, no execution.

## 6. Risk Model
The scanner must report and monitor:
- **Funding Flip Risk**: Funding changing sign against the position.
- **Basis Widening Risk**: Basis moving against the convergence/carry trade.
- **Liquidation Risk**: Price movement exceeding margin buffer.
- **Exchange/Counterparty Risk**.
- **Borrow Risk**: Cost or availability of spot margin.
- **Slippage/Liquidity Risk**: Impact of entering/exiting positions.
- **API/Data Staleness Risk**: Using outdated price/funding data.
- **Capital Lockup Risk**.

## 7. Conservative Assumptions
By default, use conservative estimates:
- Spot fee bps: (e.g., 10 bps)
- Perp fee bps: (e.g., 5 bps)
- Slippage bps: (e.g., 2-5 bps per leg)
- Funding uncertainty buffer.
- Minimum net carry threshold for "candidate" status.
- Minimum liquidity threshold.

## 8. Success Gate (Candidate Opportunity)
An opportunity is only marked as a "candidate" if:
- Net expected carry after conservative costs is positive.
- Liquidity is sufficient for the target size.
- Spread is not too wide.
- Data is fresh (no stale timestamps).
- Liquidation buffer is acceptable.
- Not dependent on a single anomalous data point.

## 9. Kill Criteria
Stop or block the research if:
- Data timestamps are not causal.
- Funding timestamps are ambiguous.
- Mark/spot data is stale.
- Expected carry disappears after realistic fees.
- Opportunities are too rare or illiquid.
- Scanner cannot reproduce historical funding/basis correctly.

## 10. No Deployment Rule
No live trading or automatic execution until:
- Historical scanner is validated.
- Paper/dry-run scanner runs for at least 30 days.
- Realized vs expected carry is audited.
- Risk model is thoroughly reviewed.
