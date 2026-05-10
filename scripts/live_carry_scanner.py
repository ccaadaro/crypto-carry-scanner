import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

# Configuration
BASE_DIR = Path("/home/nosferatu/freqtrade/user_data/strategies/crypto_carry_scanner")
REPORTS_DIR = BASE_DIR / "reports/carry"

# Assumptions (matching CARRY-2)
SPOT_FEE_BPS = 10
PERP_FEE_BPS = 10
ROUNDTRIP_FEE_BPS = 20
SLIPPAGE_BPS = 20
RISK_BUFFER_BPS = 20
MIN_NET_EXPECTED_CARRY_BPS = 25

def fetch_live_data():
    print("Fetching live data from Binance...")
    exchange = ccxt.binance({'enableRateLimit': True})
    
    symbols = [
        {"spot": "BTC/USDT", "perp": "BTC/USDT:USDT"},
        {"spot": "ETH/USDT", "perp": "ETH/USDT:USDT"}
    ]
    
    rows = []
    
    for pair in symbols:
        try:
            spot_sym = pair["spot"]
            perp_sym = pair["perp"]
            
            # 1. Fetch Spot Ticker
            spot_ticker = exchange.fetch_ticker(spot_sym)
            spot_price = spot_ticker['last']
            
            # 2. Fetch Perp Ticker & Funding
            funding_data = exchange.fetch_funding_rate(perp_sym)
            perp_ticker = exchange.fetch_ticker(perp_sym)
            
            perp_mark_price = perp_ticker['last']
            funding_rate = funding_data['fundingRate']
            index_price = funding_data.get('indexPrice')
            
            # Binance uses 'fundingTimestamp' for the next settlement time
            next_funding_time = funding_data.get('nextFundingTimestamp') or funding_data.get('fundingTimestamp')
            
            # 3. Fetch recent OHLCV for basis averages (Last 7 days)
            # We'll get 1h bars to be efficient
            since = exchange.milliseconds() - (7 * 24 * 60 * 60 * 1000)
            spot_ohlcv = exchange.fetch_ohlcv(spot_sym, timeframe='1h', since=since)
            perp_ohlcv = exchange.fetch_ohlcv(perp_sym, timeframe='1h', since=since)
            
            spot_df = pd.DataFrame(spot_ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
            perp_df = pd.DataFrame(perp_ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
            
            # Align and compute basis
            hist_basis = (perp_df['c'] - spot_df['c']) / spot_df['c']
            basis_ann_1d = hist_basis.tail(24).mean() * 365
            basis_ann_7d = hist_basis.mean() * 365
            
            # 4. Compute Metrics
            basis_bps = ((perp_mark_price - spot_price) / spot_price) * 10000
            funding_annualized = funding_rate * 3 * 365
            funding_annualized_bps = funding_annualized * 10000
            
            # Net expected carry (Annualized BPS)
            expected_hold_days = 7
            amortized_cost_bps = (ROUNDTRIP_FEE_BPS + SLIPPAGE_BPS) * (365 / expected_hold_days)
            net_expected_carry_bps = funding_annualized_bps - amortized_cost_bps - RISK_BUFFER_BPS
            
            # Candidate Rule
            candidate_flag = False
            rejection_reason = ""
            
            if net_expected_carry_bps < MIN_NET_EXPECTED_CARRY_BPS:
                rejection_reason = "low_carry"
            elif abs(basis_bps) > 500:
                rejection_reason = "extreme_basis"
            else:
                candidate_flag = True
            
            nft_str = "N/A"
            if next_funding_time:
                nft_str = datetime.fromtimestamp(next_funding_time / 1000, timezone.utc).isoformat()

            rows.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": spot_sym,
                "spot_price": spot_price,
                "perp_mark_price": perp_mark_price,
                "index_price": index_price,
                "funding_rate": funding_rate,
                "next_funding_time": nft_str,
                "basis_bps": basis_bps,
                "funding_annualized": funding_annualized,
                "basis_ann_1d": basis_ann_1d,
                "basis_ann_7d": basis_ann_7d,
                "estimated_fee_bps": ROUNDTRIP_FEE_BPS,
                "estimated_slippage_bps": SLIPPAGE_BPS,
                "risk_buffer_bps": RISK_BUFFER_BPS,
                "net_expected_carry_bps": net_expected_carry_bps,
                "liquidity_score": 1.0, 
                "stale_data_flag": False,
                "candidate_flag": candidate_flag,
                "rejection_reason": rejection_reason
            })
            
        except Exception as e:
            print(f"Error fetching data for {pair}: {e}")
            
    return pd.DataFrame(rows)

def main():
    print("=== PHASE CARRY-3: Live Scanner ===")
    
    df = fetch_live_data()
    
    if df.empty:
        print("CRITICAL: No live data fetched.")
        return
        
    # Save CSV
    output_path = REPORTS_DIR / "live_opportunities.csv"
    df.to_csv(output_path, index=False)
    print(f"Saved live scan to: {output_path}")
    
    # Print ranked results
    print("\nLive Carry Opportunities (Ranked by Net Carry):")
    ranked = df.sort_values("net_expected_carry_bps", ascending=False)
    print(ranked[["symbol", "funding_rate", "basis_bps", "net_expected_carry_bps", "candidate_flag", "rejection_reason"]])
    
    # Status
    if any(df["candidate_flag"]):
        print("\nStatus: PASS (Candidates found)")
    else:
        print("\nStatus: FAIL (No candidates meet threshold)")

if __name__ == "__main__":
    main()
