#!/usr/bin/env python3
import argparse
import os
from datetime import datetime, timedelta
from src.common.logger import get_logger, timed

def run_pipeline(provider: str, symbol: str, timeframe: str, days_back: int, store_db: bool, save_files: bool):
    logger = get_logger("pipeline")
    with timed(logger, "run_pipeline"):
        logger.info(f"provider={provider} symbol={symbol} tf={timeframe} days_back={days_back} store_db={store_db} save_files={save_files}")
        # TODO: integrate with your existing ingestion + transform + load functions
        # Example placeholders:
        # data = ingest(provider, symbol, timeframe, start=..., end=...)
        # df = transform(data)
        # if save_files: df.to_parquet(...)
        # if store_db: load_to_db(df)
        logger.info("pipeline finished")

def main():
    parser = argparse.ArgumentParser(description="Run financial data pipeline")
    parser.add_argument("--provider", default="bybit")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", default="1h", choices=["1m","5m","15m","1h","4h","1d"])
    parser.add_argument("--days-back", type=int, default=7)
    parser.add_argument("--store-db", action="store_true")
    parser.add_argument("--save-files", action="store_true")
    args = parser.parse_args()
    run_pipeline(args.provider, args.symbol, args.timeframe, args.days_back, args.store_db, args.save_files)

if __name__ == "__main__":
    main()
