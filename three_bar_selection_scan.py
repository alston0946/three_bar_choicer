# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = [
    "ticker",
    "ts_code",
    "name",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "pct_chg",
    "ma5",
    "ma10",
    "ma20",
    "ma30",
    "ma60",
    "ma250",
    "vol_ma20",
    "high_30_prev",
    "bar_range_abs",
    "sw_l1_close",
    "sw_l1_ma20",
]

CANDIDATE_COLUMNS = [
    "ticker",
    "ts_code",
    "name",
    "setup_type",
    "ignite_date",
    "target_date",
    "board_type",
    "long_ma_status",
    "industry_above_ma20",
    "ignite_pct_chg_pct",
    "ignite_upper_shadow_pct",
    "ignite_close_vs_30d_high_pct",
    "ignite_volume_vs_ma20",
    "ignite_high",
    "ignite_close",
    "ma5",
    "ma10",
    "ma20",
    "ma30",
    "ma60",
    "ma250",
    "invalid_price",
    "rest_dates",
    "rest_avg_volume_ratio",
    "rest_max_range_ratio",
    "rest_max_upper_shadow_pct",
    "rest_max_high",
    "rest_max_close",
    "rest_lowest_close_vs_invalid_pct",
]

UPPER_SHADOW_LIMIT = 0.022


def normalize_date_str(value: str) -> str:
    digits = "".join(ch for ch in str(value).strip() if ch.isdigit())
    if len(digits) != 8:
        raise ValueError(f"invalid date: {value}")
    return digits


def is_20cm(ts_code: str) -> bool:
    code = str(ts_code).split(".")[0]
    return code.startswith(("300", "301", "688"))


def long_ma_status(ma60: float, ma250: float) -> str:
    ma60_ok = pd.notna(ma60)
    ma250_ok = pd.notna(ma250)
    if ma60_ok and ma250_ok:
        return "complete"
    if (not ma60_ok) and (not ma250_ok):
        return "missing_both"
    if not ma60_ok:
        return "missing_ma60"
    return "missing_ma250"


def industry_above_ma20(sw_l1_close: float, sw_l1_ma20: float):
    if pd.isna(sw_l1_close) or pd.isna(sw_l1_ma20):
        return pd.NA
    return bool(float(sw_l1_close) >= float(sw_l1_ma20))


def load_data(input_file: Path) -> pd.DataFrame:
    df = pd.read_csv(input_file, encoding="utf-8-sig", low_memory=False)
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"input file missing columns: {missing}")

    df["trade_date"] = df["trade_date"].astype(str).str.replace(r"\D", "", regex=True)
    df["date_dt"] = pd.to_datetime(df["trade_date"], format="%Y%m%d", errors="coerce")
    df = df[df["date_dt"].notna()].copy()
    df = df[~df["ts_code"].astype(str).str.upper().str.endswith(".BJ")].copy()
    df = df.sort_values(["ts_code", "date_dt"]).reset_index(drop=True)

    num_cols = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "pct_chg",
        "ma5",
        "ma10",
        "ma20",
        "ma30",
        "ma60",
        "ma250",
        "vol_ma20",
        "high_30_prev",
        "bar_range_abs",
        "sw_l1_close",
        "sw_l1_ma20",
    ]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.extract(r"(\d+)", expand=False).fillna("").str.zfill(6)
    return df


def scan_candidates(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for ts_code, group in df.groupby("ts_code", sort=False):
        group = group.reset_index(drop=True)
        if len(group) < 2:
            continue

        board_20 = is_20cm(ts_code)
        ignite_min_pct = 0.04 if board_20 else 0.03

        for i in range(len(group) - 1):
            row = group.iloc[i]

            opn = row["open"]
            high = row["high"]
            close = row["close"]
            volume = row["volume"]
            vol_ma20 = row["vol_ma20"]
            high_30_prev = row["high_30_prev"]
            ma5 = row["ma5"]
            ma10 = row["ma10"]
            ma20 = row["ma20"]
            ma60 = row["ma60"]
            ma250 = row["ma250"]
            pct_chg = row["pct_chg"]
            bar_range = row["bar_range_abs"]
            sw_l1_close = row["sw_l1_close"]
            sw_l1_ma20 = row["sw_l1_ma20"]

            if pd.isna(opn) or opn == 0 or pd.isna(high) or pd.isna(close):
                continue

            upper_shadow_pct = (high - max(opn, close)) / opn
            near_high_ratio = close / high_30_prev if pd.notna(high_30_prev) and high_30_prev > 0 else pd.NA
            lm_status = long_ma_status(ma60, ma250)

            close_vs_long_ok = True
            long_ma_order_ok = True
            if pd.notna(ma60):
                close_vs_long_ok = close_vs_long_ok and close >= ma60
                long_ma_order_ok = long_ma_order_ok and ma60 < ma5 and ma60 < ma10
            if pd.notna(ma250):
                close_vs_long_ok = close_vs_long_ok and close >= ma250
                long_ma_order_ok = long_ma_order_ok and ma250 < ma5 and ma250 < ma10

            ignite_checks = [
                close > opn,
                pd.notna(pct_chg) and float(pct_chg) >= ignite_min_pct,
                pd.notna(ma5) and pd.notna(ma10) and pd.notna(ma20) and close >= ma5 and close >= ma10 and close >= ma20,
                close_vs_long_ok,
                pd.notna(ma5) and pd.notna(ma10) and pd.notna(ma20) and ma5 > ma10 and ma5 > ma20,
                long_ma_order_ok,
                pd.notna(high_30_prev) and high_30_prev > 0 and close >= high_30_prev,
                pd.notna(vol_ma20) and vol_ma20 > 0 and volume >= vol_ma20,
                pd.notna(upper_shadow_pct) and upper_shadow_pct <= UPPER_SHADOW_LIMIT,
                pd.notna(bar_range) and bar_range > 0,
            ]
            if not all(ignite_checks):
                continue

            invalid_price = (opn + close) / 2.0
            for rest_count in (1, 2):
                if i + rest_count >= len(group):
                    continue

                pullback = group.iloc[i + 1 : i + 1 + rest_count].copy()
                if len(pullback) != rest_count:
                    continue

                pb_shadow = (pullback["high"] - pullback[["open", "close"]].max(axis=1)) / pullback["open"]
                rest_avg_vol_ratio = pullback["volume"].mean() / volume if volume and not pd.isna(volume) else pd.NA
                rest_max_range_ratio = pullback["bar_range_abs"].max() / bar_range if bar_range and not pd.isna(bar_range) else pd.NA

                rest_checks = [
                    bool((pb_shadow <= UPPER_SHADOW_LIMIT).all()),
                    pd.notna(rest_avg_vol_ratio) and float(rest_avg_vol_ratio) < 1.0,
                    pd.notna(rest_max_range_ratio) and float(rest_max_range_ratio) < 0.70,
                    bool((pullback["close"] >= invalid_price).all()),
                    bool((pullback["close"] <= high).all()),
                ]
                if not all(rest_checks):
                    continue

                target = pullback.iloc[-1]
                rows.append(
                    {
                        "ticker": str(row["ticker"]).zfill(6),
                        "ts_code": ts_code,
                        "name": row["name"],
                        "setup_type": f"A{rest_count - 1}_第{rest_count}根整理",
                        "ignite_date": row["trade_date"],
                        "target_date": target["trade_date"],
                        "board_type": "20cm" if board_20 else "10cm",
                        "long_ma_status": lm_status,
                        "industry_above_ma20": industry_above_ma20(sw_l1_close, sw_l1_ma20),
                        "ignite_pct_chg_pct": round(float(pct_chg) * 100, 2),
                        "ignite_upper_shadow_pct": round(float(upper_shadow_pct) * 100, 2),
                        "ignite_close_vs_30d_high_pct": round(float(near_high_ratio) * 100, 2),
                        "ignite_volume_vs_ma20": round(float(volume / vol_ma20), 2),
                        "ignite_high": round(float(high), 3),
                        "ignite_close": round(float(close), 3),
                        "ma5": round(float(ma5), 3),
                        "ma10": round(float(ma10), 3),
                        "ma20": round(float(ma20), 3),
                        "ma30": round(float(row["ma30"]), 3) if pd.notna(row["ma30"]) else pd.NA,
                        "ma60": round(float(ma60), 3) if pd.notna(ma60) else pd.NA,
                        "ma250": round(float(ma250), 3) if pd.notna(ma250) else pd.NA,
                        "invalid_price": round(float(invalid_price), 3),
                        "rest_dates": "/".join(pullback["trade_date"].astype(str).tolist()),
                        "rest_avg_volume_ratio": round(float(rest_avg_vol_ratio), 4),
                        "rest_max_range_ratio": round(float(rest_max_range_ratio), 4),
                        "rest_max_upper_shadow_pct": round(float(pb_shadow.max()) * 100, 2),
                        "rest_max_high": round(float(pullback["high"].max()), 3),
                        "rest_max_close": round(float(pullback["close"].max()), 3),
                        "rest_lowest_close_vs_invalid_pct": round(float((pullback["close"].min() / invalid_price - 1.0) * 100), 2),
                    }
                )

    if not rows:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS).sort_values(["target_date", "ticker", "setup_type"]).reset_index(drop=True)


def build_stats(df: pd.DataFrame, target_date: str | None) -> dict:
    long_ma_counts = {}
    industry_counts = {}
    if not df.empty and "long_ma_status" in df.columns:
        long_ma_counts = {str(k): int(v) for k, v in df["long_ma_status"].value_counts(dropna=False).items()}
    if not df.empty and "industry_above_ma20" in df.columns:
        industry_counts = {
            ("missing" if pd.isna(k) else str(k)): int(v)
            for k, v in df["industry_above_ma20"].value_counts(dropna=False).items()
        }
    return {
        "target_date": target_date or "",
        "candidate_count": int(len(df)),
        "long_ma_status_counts": long_ma_counts,
        "industry_above_ma20_counts": industry_counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan 3-bar selection candidates from prepared daily data.")
    parser.add_argument("--input-file", required=True, help="Prepared daily CSV path.")
    parser.add_argument("--output-file", required=True, help="Output candidate CSV path.")
    parser.add_argument("--target-date", help="Optional YYYYMMDD filter for target_date.")
    parser.add_argument("--stats-json", help="Optional JSON output for summary stats.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_file = Path(args.input_file)
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    target_date = normalize_date_str(args.target_date) if args.target_date else None
    df = load_data(input_file)
    out = scan_candidates(df)
    if target_date:
        out = out[out["target_date"].astype(str) == target_date].reset_index(drop=True)

    out.to_csv(output_file, index=False, encoding="utf-8-sig")

    stats = build_stats(out, target_date)
    if args.stats_json:
        stats_path = Path(args.stats_json)
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print("candidate_count=", len(out))
    print("output_file=", output_file.resolve())
    print("long_ma_status_counts:")
    print(pd.Series(stats["long_ma_status_counts"]).to_string() if stats["long_ma_status_counts"] else "{}")
    print("industry_above_ma20_counts:")
    print(pd.Series(stats["industry_above_ma20_counts"]).to_string() if stats["industry_above_ma20_counts"] else "{}")


if __name__ == "__main__":
    main()
