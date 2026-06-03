# -*- coding: utf-8 -*-

import argparse
import json
import traceback
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pandas as pd

from send_email import build_email_subject, build_summary_body, send_email
from three_bar_selection_scan import build_stats, load_data, scan_candidates
from tushare_data import build_prepared_daily_dataset, determine_effective_trade_date_from_csv, normalize_date_str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily 3-bar selection and optionally send QQ email.")
    parser.add_argument("--run-date", help="Requested run date in YYYYMMDD. Defaults to today in Asia/Shanghai.")
    parser.add_argument("--output-dir", default="artifacts", help="Output directory.")
    parser.add_argument("--local-input-csv", help="Use an existing prepared CSV instead of pulling from Tushare.")
    parser.add_argument("--lookback-days", type=int, default=520, help="Calendar lookback days for Tushare fetch.")
    parser.add_argument(
        "--keep-prepared-data",
        action="store_true",
        help="Persist prepared_daily_data.csv in the output directory for debugging.",
    )
    parser.add_argument("--send-email", action="store_true", help="Send email after files are generated.")
    return parser.parse_args()


def top_candidates_for_summary(df: pd.DataFrame, limit: int = 20) -> list[dict]:
    cols = [
        "ticker",
        "name",
        "setup_type",
        "board_type",
        "ignite_pct_chg_pct",
        "industry_above_ma20",
    ]
    if df.empty:
        return []
    subset = df.loc[:, [col for col in cols if col in df.columns]].head(limit).copy()
    subset = subset.where(pd.notna(subset), None)
    return subset.to_dict(orient="records")


def build_mail_summary(
    requested_run_date: str,
    effective_trade_date: str,
    candidates: pd.DataFrame,
    output_file: Path,
) -> dict:
    stats = build_stats(candidates, effective_trade_date)
    return {
        "requested_run_date": requested_run_date,
        "effective_trade_date": effective_trade_date,
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
        "candidate_count": int(len(candidates)),
        "industry_above_ma20_counts": stats["industry_above_ma20_counts"],
        "output_file": str(output_file),
        "top_candidates": top_candidates_for_summary(candidates, limit=20),
    }


def build_failure_summary(requested_run_date: str, exc: Exception) -> dict:
    return {
        "requested_run_date": requested_run_date,
        "effective_trade_date": "",
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
        "candidate_count": 0,
        "industry_above_ma20_counts": {},
        "output_file": "",
        "top_candidates": [],
        "status": "failed",
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }


def main() -> None:
    args = parse_args()
    requested_run_date = normalize_date_str(args.run_date)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prepared_file = output_dir / "prepared_daily_data.csv"
    candidates_file = output_dir / "three_bar_selection_candidates.csv"
    summary_file = output_dir / "mail_summary.json"
    traceback_file = output_dir / "error_traceback.txt"
    temp_prepared_dir: TemporaryDirectory | None = None

    try:
        if args.local_input_csv:
            data_input = Path(args.local_input_csv)
            effective_trade_date = determine_effective_trade_date_from_csv(data_input, requested_run_date)
            prepare_meta = {
                "mode": "local_input_csv",
                "requested_run_date": requested_run_date,
                "effective_trade_date": effective_trade_date,
                "output_file": str(data_input),
                "output_persisted": True,
            }
        else:
            if args.keep_prepared_data:
                prepared_output_path = prepared_file
            else:
                temp_prepared_dir = TemporaryDirectory()
                prepared_output_path = Path(temp_prepared_dir.name) / prepared_file.name

            prepare_meta = build_prepared_daily_dataset(
                run_date=requested_run_date,
                output_path=prepared_output_path,
                lookback_days=args.lookback_days,
            )
            effective_trade_date = prepare_meta["effective_trade_date"]
            data_input = Path(prepare_meta["output_file"])
            prepare_meta["output_persisted"] = bool(args.keep_prepared_data)
            if not args.keep_prepared_data:
                prepare_meta["output_file"] = None

        data = load_data(data_input)
        candidates = scan_candidates(data)
        candidates = candidates[candidates["target_date"].astype(str) == effective_trade_date].reset_index(drop=True)
        candidates.to_csv(candidates_file, index=False, encoding="utf-8-sig")

        summary = build_mail_summary(
            requested_run_date=requested_run_date,
            effective_trade_date=effective_trade_date,
            candidates=candidates,
            output_file=candidates_file,
        )
        summary["prepare_meta"] = prepare_meta
        summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        print("requested_run_date=", requested_run_date)
        print("effective_trade_date=", effective_trade_date)
        if "calendar_last_trade_date" in prepare_meta:
            print("calendar_last_trade_date=", prepare_meta["calendar_last_trade_date"])
        if "data_last_trade_date" in prepare_meta:
            print("data_last_trade_date=", prepare_meta["data_last_trade_date"])
        if "skipped_same_day_fetch" in prepare_meta:
            print("skipped_same_day_fetch=", prepare_meta["skipped_same_day_fetch"])
        print("candidate_count=", len(candidates))
        print("prepared_data_persisted=", prepare_meta.get("output_persisted"))
        if args.keep_prepared_data:
            print("prepared_data_file=", prepared_file.resolve())
        print("candidates_file=", candidates_file.resolve())
        print("summary_file=", summary_file.resolve())

        if args.send_email:
            body = build_summary_body(summary)
            subject = build_email_subject(summary)
            send_email(subject=subject, body=body, attachments=[candidates_file])
            print("email_sent=True")
    except Exception as exc:
        failure_summary = build_failure_summary(requested_run_date, exc)
        summary_file.write_text(json.dumps(failure_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        traceback_text = traceback.format_exc()
        traceback_file.write_text(traceback_text, encoding="utf-8")
        print("run_status=failed")
        print(f"error_type={type(exc).__name__}")
        print(f"error_message={exc}")
        print("traceback_file=", traceback_file.resolve())
        raise
    finally:
        if temp_prepared_dir is not None:
            temp_prepared_dir.cleanup()


if __name__ == "__main__":
    main()
