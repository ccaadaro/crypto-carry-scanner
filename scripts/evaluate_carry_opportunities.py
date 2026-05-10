import pandas as pd
import numpy as np
from pathlib import Path

# Configuration
BASE_DIR = Path("/home/nosferatu/freqtrade/user_data/strategies/crypto_carry_scanner")
CACHE_DIR = BASE_DIR / "cache/carry"
REPORTS_DIR = BASE_DIR / "reports/carry"

# Conservative Assumptions
SPOT_FEE_BPS = 10
PERP_FEE_BPS = 10
ROUNDTRIP_FEE_BPS = SPOT_FEE_BPS + PERP_FEE_BPS # 20 bps
SLIPPAGE_BPS = 20
RISK_BUFFER_BPS = 20
MIN_NET_EXPECTED_CARRY_BPS = 25

def evaluate_opportunities(df):
    print("Evaluating opportunities...")
    
    # 1. Compute Opportunity Metrics
    # Expected gross carry (annualized)
    df["funding_annualized_bps"] = df["funding_annualized"] * 10000
    df["basis_ann_7d_bps"] = df["basis_ann_7d"] * 10000
    
    # Total expected carry (funding + basis convergence assumption)
    # Conservative: only look at funding for the 'expected' part
    df["gross_expected_carry_bps"] = df["funding_annualized_bps"]
    
    # Subtract costs
    df["estimated_fee_bps"] = ROUNDTRIP_FEE_BPS
    df["estimated_slippage_bps"] = SLIPPAGE_BPS
    df["risk_buffer_bps"] = RISK_BUFFER_BPS
    
    # Total drag in BPS (annualized for comparison with gross_expected_carry_bps)
    # This is tricky: fees are flat, carry is annualized.
    # To compare them, we need an expected hold time.
    # Let's assume a 7-day minimum hold for the 'expected' net calculation.
    expected_hold_days = 7
    amortized_cost_bps = (df["estimated_fee_bps"] + df["estimated_slippage_bps"]) * (365 / expected_hold_days)
    
    df["net_expected_carry_bps"] = df["gross_expected_carry_bps"] - amortized_cost_bps - df["risk_buffer_bps"]
    
    # 2. Candidate Flagging
    # Rule: 
    # - Net carry > threshold
    # - Data not stale
    # - Basis is not extremely negative (avoid entering when spot is much more expensive than perp)
    
    df["candidate_flag"] = (
        (df["net_expected_carry_bps"] > MIN_NET_EXPECTED_CARRY_BPS) &
        (df["is_stale_data"] == False) &
        (df["basis_bps"] > -50) # Avoid extreme backwardation for carry
    )
    
    return df

def run_backtest(df):
    print("Running historical simulation (Backtest)...")
    
    backtest_results = []
    opportunity_events = []
    all_equity_curves = []
    
    symbols = df["symbol"].unique()
    
    for symbol in symbols:
        sym_df = df[df["symbol"] == symbol].sort_values("date").copy()
        if sym_df.empty:
            continue
            
        in_position = False
        entry_price_spot = 0
        entry_price_perp = 0
        entry_date = None
        entry_basis = 0
        
        cumulative_pnl_bps = 0
        peak_pnl_bps = 0
        max_drawdown_bps = 0
        max_adverse_basis_move = 0
        
        equity_curve = []
        
        for i in range(len(sym_df)):
            row = sym_df.iloc[i]
            current_date = row["date"]
            
            if in_position:
                # 1. Update Funding PnL
                if i > 0 and row["funding_timestamp"] != sym_df.iloc[i-1]["funding_timestamp"]:
                    funding_earned_bps = row["funding_rate"] * 10000
                    cumulative_pnl_bps += funding_earned_bps
                
                # 2. Update Basis MTM
                current_basis_bps = row["basis_bps"]
                mtm_pnl_bps = (entry_basis_bps - current_basis_bps)
                
                # Track adverse basis move
                # If basis increases, MTM decreases. Adverse move = current_basis - entry_basis if > 0
                adverse_move = current_basis_bps - entry_basis_bps
                if adverse_move > max_adverse_basis_move:
                    max_adverse_basis_move = adverse_move
                
                # 3. Check Exit Condition
                # Exit if net carry becomes significantly unattractive or very negative
                # Use hysteresis to prevent flipping
                exit_threshold = -100 # Allow some negative carry before exiting
                exit_condition = row["net_expected_carry_bps"] < exit_threshold
                
                if exit_condition:
                    # Subtract exit costs (half of roundtrip + half of slippage)
                    exit_cost_bps = (ROUNDTRIP_FEE_BPS / 2) + (SLIPPAGE_BPS / 2)
                    cumulative_pnl_bps -= exit_cost_bps
                    cumulative_pnl_bps += mtm_pnl_bps # Realize MTM
                    
                    opportunity_events.append({
                        "symbol": symbol,
                        "entry_date": entry_date,
                        "exit_date": current_date,
                        "duration_hours": (current_date - entry_date).total_seconds() / 3600,
                        "final_pnl_bps": cumulative_pnl_bps - trade_start_pnl,
                        "exit_reason": "negative_carry"
                    })
                    
                    in_position = False
                    mtm_pnl_bps = 0
            
            # 4. Check Entry Condition
            if not in_position and row["candidate_flag"]:
                in_position = True
                entry_price_spot = row["spot_close"]
                entry_price_perp = row["perp_mark_close"]
                entry_date = current_date
                entry_basis_bps = row["basis_bps"]
                trade_start_pnl = cumulative_pnl_bps
                
                # Subtract entry costs
                entry_cost_bps = (ROUNDTRIP_FEE_BPS / 2) + (SLIPPAGE_BPS / 2)
                cumulative_pnl_bps -= entry_cost_bps
                mtm_pnl_bps = 0
                
            current_total_pnl = cumulative_pnl_bps + (mtm_pnl_bps if in_position else 0)
            
            # Track Drawdown
            if current_total_pnl > peak_pnl_bps:
                peak_pnl_bps = current_total_pnl
            
            dd = peak_pnl_bps - current_total_pnl
            if dd > max_drawdown_bps:
                max_drawdown_bps = dd
                
            equity_curve.append({
                "date": current_date,
                "symbol": symbol,
                "cumulative_pnl_bps": current_total_pnl,
                "in_position": in_position
            })
            
        all_equity_curves.extend(equity_curve)
        
        # Summary for symbol
        if equity_curve:
            final_pnl = equity_curve[-1]["cumulative_pnl_bps"]
            backtest_results.append({
                "symbol": symbol,
                "total_pnl_bps": final_pnl,
                "trade_count": len([e for e in opportunity_events if e["symbol"] == symbol]),
                "max_drawdown_bps": max_drawdown_bps,
                "max_adverse_basis_move_bps": max_adverse_basis_move
            })

    return pd.DataFrame(backtest_results), pd.DataFrame(opportunity_events), pd.DataFrame(all_equity_curves)

def main():
    print("=== PHASE CARRY-2: Opportunity Evaluator ===")
    
    dataset_path = CACHE_DIR / "carry_dataset.feather"
    if not dataset_path.exists():
        print(f"CRITICAL: Dataset not found. Run Phase CARRY-1.")
        return
        
    df = pd.read_feather(dataset_path)
    df = evaluate_opportunities(df)
    summary, events, equity = run_backtest(df)
    
    if not summary.empty:
        summary.to_csv(REPORTS_DIR / "backtest_summary.csv", index=False)
        events.to_csv(REPORTS_DIR / "opportunity_events.csv", index=False)
        equity.to_csv(REPORTS_DIR / "equity_curve.csv", index=False)
        
        opp_summary = df.groupby("symbol").agg({
            "candidate_flag": ["sum", "mean"],
            "net_expected_carry_bps": ["median", "max", lambda x: x.quantile(0.95)]
        }).reset_index()
        opp_summary.columns = ["symbol", "candidate_count", "candidate_freq", "median_net_carry", "max_net_carry", "p95_net_carry"]
        opp_summary.to_csv(REPORTS_DIR / "opportunity_summary.csv", index=False)
        
        print("\nOpportunity Summary:")
        print(opp_summary)
        print("\nBacktest Summary:")
        print(summary)
        
        candidate_count = opp_summary["candidate_count"].sum()
        total_pnl = summary["total_pnl_bps"].sum()
        median_net_carry = opp_summary["median_net_carry"].median()
        max_adverse_move = summary["max_adverse_basis_move_bps"].max()
        
        # Final Report Checklist
        print("\n--- Phase CARRY-2 Report ---")
        print(f"1. Candidate Opportunities: {candidate_count}")
        print(f"2. Median Net Expected Carry: {median_net_carry:.2f} bps (annualized)")
        print(f"   P95 Net Expected Carry: {opp_summary['p95_net_carry'].max():.2f} bps")
        print(f"3. Backtest Net Result: {total_pnl:.2f} bps")
        print(f"4. Worst Adverse Basis Move: {max_adverse_move:.2f} bps")
        
        is_pass = (candidate_count > 0) and (total_pnl > 0)
        status = "PASS" if is_pass else "FAIL"
        print(f"5. Final Status: {status}")
        
        if status == "PASS":
            print("6. Recommended Next Step: Proceed to PHASE CARRY-3 (Risk/Sizing Engine).")
        else:
            print("6. Recommended Next Step: Review fee/slippage assumptions or entry/exit logic. Consider higher carry thresholds.")
    else:
        print("\nFinal Status: FAIL (No summary generated)")

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
