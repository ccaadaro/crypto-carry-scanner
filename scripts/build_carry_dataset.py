import pandas as pd
import numpy as np
from pathlib import Path
import os

# Configuration
BASE_DIR = Path("/home/nosferatu/freqtrade/user_data/strategies/crypto_carry_scanner")
DATA_DIR = Path("/home/nosferatu/freqtrade/user_data/data/binance")
CACHE_DIR = BASE_DIR / "cache/carry"
REPORTS_DIR = BASE_DIR / "reports/carry"

SYMBOLS = ["BTC/USDT", "ETH/USDT"]
TIMEFRAME_SPOT = "1h"
TIMEFRAME_FUTURES = "8h"

def get_spot_path(symbol):
    clean_sym = symbol.replace("/", "_")
    return DATA_DIR / f"{clean_sym}-{TIMEFRAME_SPOT}.feather"

def get_perp_path(symbol, data_type):
    # Freqtrade futures naming convention: SYMBOL_USDT_USDT-TIMEFRAME-TYPE.feather
    # e.g. BTC_USDT_USDT-8h-mark.feather
    clean_sym = symbol.replace("/", "_")
    return DATA_DIR / "futures" / f"{clean_sym}_USDT-{TIMEFRAME_FUTURES}-{data_type}.feather"

def load_data():
    all_data = []
    data_audit = []
    
    for symbol in SYMBOLS:
        print(f"Processing {symbol}...")
        
        # Paths
        spot_path = get_spot_path(symbol)
        mark_path = get_perp_path(symbol, "mark")
        funding_path = get_perp_path(symbol, "funding_rate")
        futures_ohlcv_path = get_perp_path(symbol, "futures")
        
        # Check existence
        files = {
            "spot": spot_path,
            "mark": mark_path,
            "funding": funding_path,
            "futures_ohlcv": futures_ohlcv_path
        }
        
        missing = [k for k, v in files.items() if not v.exists()]
        if missing:
            print(f"  MISSING data for {symbol}: {missing}")
        
        # Load available data
        df_spot = pd.read_feather(spot_path) if spot_path.exists() else pd.DataFrame()
        df_mark = pd.read_feather(mark_path) if mark_path.exists() else pd.DataFrame()
        df_funding = pd.read_feather(funding_path) if funding_path.exists() else pd.DataFrame()
        df_perp_ohlcv = pd.read_feather(futures_ohlcv_path) if futures_ohlcv_path.exists() else pd.DataFrame()
        
        if df_spot.empty or df_mark.empty:
            print(f"  Skipping {symbol} due to critical missing data.")
            # Record in audit
            data_audit.append({
                "symbol": symbol,
                "first_timestamp": None,
                "last_timestamp": None,
                "row_count": 0,
                "missing_spot_pct": 1.0 if df_spot.empty else 0.0,
                "missing_mark_pct": 1.0 if df_mark.empty else 0.0,
                "missing_funding_pct": 1.0 if df_funding.empty else 0.0,
                "duplicate_timestamp_count": 0,
                "stale_spot_count": 0,
                "stale_mark_count": 0,
                "negative_lag_count": 0
            })
            continue

        # Rename columns to avoid collisions
        df_spot = df_spot.rename(columns={"close": "spot_close", "volume": "volume_spot"})
        df_mark = df_mark.rename(columns={"close": "perp_mark_close"})
        if not df_perp_ohlcv.empty:
            # quote_volume = volume * close approx, or if 'volume' is already quote
            df_perp_ohlcv = df_perp_ohlcv.rename(columns={"volume": "volume_perp"})
        
        # Standardize date format (Freqtrade feather usually uses 'date' as datetime)
        for df in [df_spot, df_mark, df_funding, df_perp_ohlcv]:
            if not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])

        # Merge strategy:
        # We use spot as the primary timeline (usually higher resolution)
        # and merge perp data onto it using forward fill to ensure causality.
        
        # Sort
        df_spot = df_spot.sort_values("date")
        df_mark = df_mark.sort_values("date")
        if not df_funding.empty:
            df_funding = df_funding.sort_values("date")
        
        # Merge
        merged = pd.merge_asof(df_spot, df_mark[["date", "perp_mark_close"]], on="date", direction="backward")
        
        if not df_funding.empty:
            # Freqtrade funding rate files may use 'open' or 'close' for the funding rate
            # In this environment, 'open' contains the actual rate
            df_funding = df_funding.rename(columns={"date": "funding_timestamp", "open": "funding_rate"})
            merged = pd.merge_asof(merged, df_funding[["funding_timestamp", "funding_rate"]], left_on="date", right_on="funding_timestamp", direction="backward")
        else:
            merged["funding_rate"] = np.nan
            merged["funding_timestamp"] = pd.NaT

        if not df_perp_ohlcv.empty:
             merged = pd.merge_asof(merged, df_perp_ohlcv[["date", "volume_perp"]], on="date", direction="backward")
        else:
             merged["volume_perp"] = np.nan

        # Metrics
        merged["symbol"] = symbol
        merged["basis"] = (merged["perp_mark_close"] - merged["spot_close"]) / merged["spot_close"]
        merged["basis_bps"] = merged["basis"] * 10000
        
        # Annualization
        # Funding is usually 8h -> 3 times per day
        merged["funding_annualized"] = merged["funding_rate"] * 3 * 365
        merged["basis_ann_1d"] = merged["basis"] * 365
        merged["basis_ann_7d"] = merged["basis"] * 365 / 7
        
        # Data staleness / lag
        # Lag between current row timestamp and source data timestamp
        merged["data_lag_seconds"] = (merged["date"] - merged["funding_timestamp"]).dt.total_seconds()
        merged["is_stale_data"] = merged["data_lag_seconds"] > (8 * 3600) # Funding more than 8h old
        
        # Audit counts
        row_count = len(merged)
        stale_spot = merged["spot_close"].isna().sum()
        stale_mark = merged["perp_mark_close"].isna().sum()
        
        # Negative lag check
        negative_lags = merged[merged["data_lag_seconds"] < 0]
        neg_lag_count = len(negative_lags)
        
        data_audit.append({
            "symbol": symbol,
            "first_timestamp": merged["date"].min(),
            "last_timestamp": merged["date"].max(),
            "row_count": row_count,
            "missing_spot_pct": merged["spot_close"].isna().mean(),
            "missing_mark_pct": merged["perp_mark_close"].isna().mean(),
            "missing_funding_pct": merged["funding_rate"].isna().mean(),
            "duplicate_timestamp_count": merged["date"].duplicated().sum(),
            "stale_spot_count": stale_spot,
            "stale_mark_count": stale_mark,
            "negative_lag_count": neg_lag_count
        })
        
        all_data.append(merged)

    if not all_data:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    full_dataset = pd.concat(all_data)
    audit_df = pd.DataFrame(data_audit)
    
    # Timestamp audit
    # Sample some rows for timestamp audit as requested
    # Or just use the whole dataset if small enough, but let's take a representative sample
    ts_audit = []
    for symbol in SYMBOLS:
        sym_df = full_dataset[full_dataset["symbol"] == symbol].tail(100) # Take last 100 rows
        for _, row in sym_df.iterrows():
            ts_audit.append({
                "symbol": symbol,
                "feature_name": "funding_rate",
                "row_timestamp": row["date"],
                "source_timestamp": row["funding_timestamp"],
                "lag_seconds": row["data_lag_seconds"],
                "negative_lag_flag": row["data_lag_seconds"] < 0
            })
    
    ts_audit_df = pd.DataFrame(ts_audit)
    
    return full_dataset, audit_df, ts_audit_df

def main():
    print("=== PHASE CARRY-1: Data Builder ===")
    
    # Ensure directories exist
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    df, audit, ts_audit = load_data()
    
    if df.empty:
        print("CRITICAL: No data loaded. Check file paths and existence.")
        # Create empty audit with MISSING report
        # Listing missing files as requested
        report_str = "MISSING FILES REPORT:\n"
        for symbol in SYMBOLS:
            for dtype in ["mark", "funding_rate", "futures"]:
                p = get_perp_path(symbol, dtype)
                if not p.exists():
                    report_str += f"- {p.name} (Expected in {p.parent})\n"
            s = get_spot_path(symbol)
            if not s.exists():
                report_str += f"- {s.name} (Expected in {s.parent})\n"
        
        print(report_str)
        with open(REPORTS_DIR / "missing_files.txt", "w") as f:
            f.write(report_str)
            
        print("Status: FAIL (No data found)")
        return

    # Check for blocked status
    is_blocked = (audit["negative_lag_count"] > 0).any()
    status = "BLOCKED" if is_blocked else "PASS"
    
    if is_blocked:
        print("!!! BLOCKED !!! Negative lag detected in timestamps.")
    
    # Save outputs
    # Feather for dataset
    df.reset_index(drop=True).to_feather(CACHE_DIR / "carry_dataset.feather")
    # CSV for audits
    audit.to_csv(REPORTS_DIR / "data_audit.csv", index=False)
    ts_audit.to_csv(REPORTS_DIR / "timestamp_audit.csv", index=False)
    
    print("\nSummary Statistics:")
    print(audit[["symbol", "row_count", "missing_funding_pct", "negative_lag_count"]])
    
    print(f"\nFinal Status: {status}")
    print(f"Dataset saved to: {CACHE_DIR / 'carry_dataset.feather'}")
    print(f"Audits saved to: {REPORTS_DIR}")

if __name__ == "__main__":
    main()
