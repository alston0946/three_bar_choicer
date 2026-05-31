# -*- coding: utf-8 -*-

import os
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)


REQUIRED_PREPARED_COLUMNS = [
    "ticker",
    "ts_code",
    "name",
    "date",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "adj_factor",
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
    "qfq_adjust_ratio",
    "price_adjust_mode",
    "pct_chg",
    "ma5",
    "ma10",
    "ma20",
    "ma30",
    "ma60",
    "ma250",
    "ma20_prev",
    "vol_ma5",
    "vol_ma20",
    "high_30_prev",
    "daily_range_pct",
    "bar_range_abs",
    "body",
    "body_ratio",
    "close_near_high",
    "sh_index_close",
    "sh_index_ma20",
    "sz_index_close",
    "sz_index_ma20",
    "sw_l1_code",
    "sw_l1_name",
    "sw_l1_close",
    "sw_l1_ma20",
]

SW_MEMBER_SLEEP_SEC = 0.10
SW_DAILY_SLEEP_SEC = 0.10


def today_in_shanghai() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")


def normalize_date_str(value: str | None) -> str:
    if not value:
        value = today_in_shanghai()
    raw = str(value).strip()
    digits = raw.replace("-", "").replace("/", "")
    if digits.endswith(".0"):
        digits = digits[:-2]
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError(f"invalid date: {value}")
    try:
        datetime.strptime(digits, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"invalid natural date: {value}") from exc
    return digits


def parse_trade_date_series(series: pd.Series) -> pd.Series:
    values = series.astype(str).str.strip()
    values = values.str.replace(r"\.0$", "", regex=True)
    values = values.str.replace("-", "", regex=False).str.replace("/", "", regex=False)
    values = values.str.zfill(8)
    return pd.to_datetime(values, format="%Y%m%d", errors="coerce")


def require_tushare_token() -> str:
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is required")
    return token


def create_tushare_client():
    token = require_tushare_token()
    try:
        import tushare as ts
    except ImportError as exc:
        raise RuntimeError("tushare package is required; install requirements.txt first") from exc
    ts.set_token(token)
    return ts.pro_api()


def fetch_with_retry(fetch_fn, empty_message: str, max_retry: int = 3, sleep_base: float = 0.8) -> pd.DataFrame:
    last_err = empty_message
    for attempt in range(max_retry):
        try:
            df = fetch_fn()
            if df is not None and not df.empty:
                return df
            last_err = empty_message
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(sleep_base + attempt * sleep_base)
    raise RuntimeError(last_err)


def fetch_trade_dates(pro, start_date: str, end_date: str) -> list[str]:
    df = fetch_with_retry(
        lambda: pro.trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1"),
        "empty trade calendar dataframe",
    )
    date_col = "cal_date" if "cal_date" in df.columns else "trade_date"
    dates = (
        df[date_col]
        .astype(str)
        .str.replace(r"\D", "", regex=True)
        .sort_values()
        .tolist()
    )
    return [date for date in dates if len(date) == 8]


def fetch_stock_basic(pro) -> pd.DataFrame:
    df = fetch_with_retry(
        lambda: pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,list_date"),
        "empty stock_basic dataframe",
    )
    out = df.copy()
    out["ts_code"] = out["ts_code"].astype(str).str.strip().str.upper()
    out["ticker"] = out["symbol"].astype(str).str.extract(r"(\d+)", expand=False).fillna("").str.zfill(6)
    out = out[~out["ts_code"].str.endswith(".BJ")].copy()
    return out[["ticker", "ts_code", "name"]].drop_duplicates("ts_code").reset_index(drop=True)


def fetch_all_stock_daily(pro, trade_dates: list[str]) -> pd.DataFrame:
    frames = []
    for trade_date in trade_dates:
        df = fetch_with_retry(
            lambda td=trade_date: pro.daily(trade_date=td),
            f"empty daily dataframe for {trade_date}",
        )
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_all_stock_adj_factor(pro, trade_dates: list[str]) -> pd.DataFrame:
    frames = []
    for trade_date in trade_dates:
        df = fetch_with_retry(
            lambda td=trade_date: pro.adj_factor(trade_date=td),
            f"empty adj_factor dataframe for {trade_date}",
        )
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def standardize_tushare_daily(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    required_cols = ["ts_code", "trade_date", "open", "high", "low", "close", "vol"]
    missing = [col for col in required_cols if col not in out.columns]
    if missing:
        raise ValueError(f"Tushare daily missing columns: {missing}")

    out["ts_code"] = out["ts_code"].astype(str).str.strip().str.upper()
    out["trade_date"] = out["trade_date"].astype(str).str.replace(r"\D", "", regex=True)
    out["date"] = parse_trade_date_series(out["trade_date"])
    out["open"] = pd.to_numeric(out["open"], errors="coerce")
    out["high"] = pd.to_numeric(out["high"], errors="coerce")
    out["low"] = pd.to_numeric(out["low"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["volume"] = pd.to_numeric(out["vol"], errors="coerce")
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce") if "amount" in out.columns else np.nan
    out["pct_chg"] = pd.to_numeric(out["pct_chg"], errors="coerce") / 100.0 if "pct_chg" in out.columns else np.nan

    out = out.dropna(subset=["ts_code", "date", "open", "high", "low", "close", "volume"]).copy()
    out = out.sort_values(["ts_code", "date"]).reset_index(drop=True)
    return out[["ts_code", "date", "trade_date", "open", "high", "low", "close", "volume", "amount", "pct_chg"]]


def standardize_tushare_adj_factor(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    required_cols = ["ts_code", "trade_date", "adj_factor"]
    missing = [col for col in required_cols if col not in out.columns]
    if missing:
        raise ValueError(f"Tushare adj_factor missing columns: {missing}")

    out["ts_code"] = out["ts_code"].astype(str).str.strip().str.upper()
    out["trade_date"] = out["trade_date"].astype(str).str.replace(r"\D", "", regex=True)
    out["date"] = parse_trade_date_series(out["trade_date"])
    out["adj_factor"] = pd.to_numeric(out["adj_factor"], errors="coerce")
    out = out.dropna(subset=["ts_code", "date", "adj_factor"]).copy()
    out = out.sort_values(["ts_code", "date"]).drop_duplicates(["ts_code", "date"], keep="last").reset_index(drop=True)
    return out[["ts_code", "date", "adj_factor"]]


def apply_qfq_adjustment(daily_df: pd.DataFrame, adj_df: pd.DataFrame) -> pd.DataFrame:
    if daily_df is None or daily_df.empty:
        return pd.DataFrame()
    if adj_df is None or adj_df.empty:
        raise ValueError("adj_factor is empty")

    out = daily_df.merge(adj_df, on=["ts_code", "date"], how="left")
    out = out.sort_values(["ts_code", "date"]).reset_index(drop=True)
    out["adj_factor"] = out.groupby("ts_code", sort=False)["adj_factor"].ffill().bfill()

    has_adj = out.groupby("ts_code", sort=False)["adj_factor"].transform(lambda s: s.notna().any())
    out = out[has_adj].copy()
    if out.empty:
        raise ValueError("all adj_factor values are missing")

    anchor_factor = out.groupby("ts_code", sort=False)["adj_factor"].transform("last")
    invalid_anchor = anchor_factor.isna() | (anchor_factor == 0)
    out = out[~invalid_anchor].copy()
    if out.empty:
        raise ValueError("all anchor adj_factor values are invalid")

    for col in ["open", "high", "low", "close"]:
        out[f"raw_{col}"] = out[col]
        out[col] = out[col] * out["adj_factor"] / anchor_factor

    out["qfq_adjust_ratio"] = out["close"] / out["raw_close"]
    out["price_adjust_mode"] = "qfq"
    out["pct_chg"] = out.groupby("ts_code", sort=False)["close"].pct_change()

    return out[
        [
            "ts_code",
            "date",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "pct_chg",
            "raw_open",
            "raw_high",
            "raw_low",
            "raw_close",
            "adj_factor",
            "qfq_adjust_ratio",
            "price_adjust_mode",
        ]
    ]


def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["ts_code", "date"]).reset_index(drop=True).copy()
    grouped = out.groupby("ts_code", sort=False)

    if "pct_chg" not in out.columns or out["pct_chg"].isna().all():
        out["pct_chg"] = grouped["close"].pct_change()

    prev_close = grouped["close"].shift(1)
    out["daily_range_pct"] = (out["high"] - out["low"]) / prev_close
    out["bar_range_abs"] = (out["high"] - out["low"]).clip(lower=1e-8)
    out["body"] = (out["close"] - out["open"]).abs()
    out["body_ratio"] = out["body"] / out["bar_range_abs"]
    out["close_near_high"] = (out["high"] - out["close"]) / out["bar_range_abs"]

    for period in [5, 10, 20, 30, 60, 250]:
        out[f"ma{period}"] = grouped["close"].transform(lambda s, p=period: s.rolling(p).mean())

    out["ma20_prev"] = grouped["ma20"].shift(1)
    out["vol_ma5"] = grouped["volume"].transform(lambda s: s.rolling(5).mean())
    out["vol_ma20"] = grouped["volume"].transform(lambda s: s.rolling(20).mean())
    out["high_30_prev"] = grouped["high"].transform(lambda s: s.rolling(30).max().shift(1))
    return out


def standardize_index_daily(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "trade_date" not in out.columns or "close" not in out.columns:
        raise ValueError(f"index data missing trade_date/close: {list(out.columns)}")
    out["trade_date"] = out["trade_date"].astype(str).str.replace(r"\D", "", regex=True)
    out["date"] = parse_trade_date_series(out["trade_date"])
    out[f"{prefix}_close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["date", f"{prefix}_close"]).sort_values("date").reset_index(drop=True)
    out[f"{prefix}_ma20"] = out[f"{prefix}_close"].rolling(20).mean()
    return out[["trade_date", "date", f"{prefix}_close", f"{prefix}_ma20"]]


def fetch_market_index_data(pro, start_date: str, end_date: str) -> pd.DataFrame:
    sh_raw = fetch_with_retry(
        lambda: pro.index_daily(ts_code="000001.SH", start_date=start_date, end_date=end_date),
        "empty SH index dataframe",
    )
    sz_raw = fetch_with_retry(
        lambda: pro.index_daily(ts_code="399001.SZ", start_date=start_date, end_date=end_date),
        "empty SZ index dataframe",
    )
    sh = standardize_index_daily(sh_raw, "sh_index")
    sz = standardize_index_daily(sz_raw, "sz_index")
    out = sh.merge(sz, on=["trade_date", "date"], how="outer").sort_values("date").reset_index(drop=True)
    return out


def fetch_sw_l1_classify(pro) -> pd.DataFrame:
    df = fetch_with_retry(
        lambda: pro.index_classify(level="L1", src="SW2021"),
        "empty SW L1 classify dataframe",
    )
    out = df.copy()
    code_col = "index_code" if "index_code" in out.columns else "ts_code"
    name_col = "industry_name" if "industry_name" in out.columns else "name"
    out["sw_l1_code"] = out[code_col].astype(str).str.strip().str.upper()
    out["sw_l1_name"] = out[name_col].astype(str).str.strip()
    return out[["sw_l1_code", "sw_l1_name"]].drop_duplicates("sw_l1_code").reset_index(drop=True)


def fetch_sw_l1_membership_map(pro, sw_l1_classify: pd.DataFrame, run_date: str) -> pd.DataFrame:
    frames = []
    for row in sw_l1_classify.itertuples(index=False):
        sw_l1_code = row.sw_l1_code
        sw_l1_name = row.sw_l1_name
        try:
            members = fetch_with_retry(
                lambda code=sw_l1_code: pro.index_member(index_code=code),
                f"empty index member dataframe for {sw_l1_code}",
            )
        except Exception as exc:
            warnings.warn(f"skip industry membership {sw_l1_code}: {exc}")
            continue

        out = members.copy()
        code_col = "con_code" if "con_code" in out.columns else "ts_code"
        if code_col not in out.columns:
            warnings.warn(f"skip industry membership {sw_l1_code}: missing con_code/ts_code")
            continue
        out["ts_code"] = out[code_col].astype(str).str.strip().str.upper()
        out["in_date"] = out.get("in_date", "").astype(str).str.replace(r"\D", "", regex=True)
        out["out_date"] = out.get("out_date", "").astype(str).str.replace(r"\D", "", regex=True)
        active = (out["in_date"] == "") | (out["in_date"] <= run_date)
        active &= (out["out_date"] == "") | (out["out_date"] >= run_date)
        out = out[active].copy()
        if out.empty:
            continue
        out["sw_l1_code"] = sw_l1_code
        out["sw_l1_name"] = sw_l1_name
        frames.append(out[["ts_code", "sw_l1_code", "sw_l1_name"]])
        time.sleep(SW_MEMBER_SLEEP_SEC)

    if not frames:
        return pd.DataFrame(columns=["ts_code", "sw_l1_code", "sw_l1_name"])
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates("ts_code", keep="last").reset_index(drop=True)


def fetch_sw_l1_daily(pro, sw_l1_classify: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    frames = []
    for row in sw_l1_classify.itertuples(index=False):
        sw_l1_code = row.sw_l1_code
        sw_l1_name = row.sw_l1_name
        try:
            raw = fetch_with_retry(
                lambda code=sw_l1_code: pro.index_daily(ts_code=code, start_date=start_date, end_date=end_date),
                f"empty industry index dataframe for {sw_l1_code}",
            )
        except Exception as exc:
            warnings.warn(f"skip industry index {sw_l1_code}: {exc}")
            continue

        out = raw.copy()
        out["trade_date"] = out["trade_date"].astype(str).str.replace(r"\D", "", regex=True)
        out["date"] = parse_trade_date_series(out["trade_date"])
        out["sw_l1_close"] = pd.to_numeric(out["close"], errors="coerce")
        out = out.dropna(subset=["date", "sw_l1_close"]).sort_values("date").reset_index(drop=True)
        out["sw_l1_ma20"] = out["sw_l1_close"].rolling(20).mean()
        out["sw_l1_code"] = sw_l1_code
        out["sw_l1_name"] = sw_l1_name
        frames.append(out[["sw_l1_code", "sw_l1_name", "trade_date", "date", "sw_l1_close", "sw_l1_ma20"]])
        time.sleep(SW_DAILY_SLEEP_SEC)

    if not frames:
        return pd.DataFrame(columns=["sw_l1_code", "sw_l1_name", "trade_date", "date", "sw_l1_close", "sw_l1_ma20"])
    return pd.concat(frames, ignore_index=True)


def ensure_required_prepared_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in REQUIRED_PREPARED_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out[REQUIRED_PREPARED_COLUMNS]


def build_prepared_daily_dataset(run_date: str, output_path: Path, lookback_days: int = 520) -> dict:
    run_date = normalize_date_str(run_date)
    end_dt = datetime.strptime(run_date, "%Y%m%d")
    start_dt = end_dt - timedelta(days=lookback_days)
    start_date = start_dt.strftime("%Y%m%d")

    pro = create_tushare_client()
    trade_dates = fetch_trade_dates(pro, start_date, run_date)
    if not trade_dates:
        raise RuntimeError("no trade dates fetched from Tushare")

    effective_trade_date = max(date for date in trade_dates if date <= run_date)

    stock_basic = fetch_stock_basic(pro)
    raw_daily = fetch_all_stock_daily(pro, trade_dates)
    raw_adj = fetch_all_stock_adj_factor(pro, trade_dates)
    daily = standardize_tushare_daily(raw_daily)
    adj = standardize_tushare_adj_factor(raw_adj)
    price = apply_qfq_adjustment(daily, adj)
    prepared = build_indicators(price)
    prepared = prepared.merge(stock_basic, on="ts_code", how="inner")

    market = fetch_market_index_data(pro, start_date, run_date)
    prepared = prepared.merge(market, on=["trade_date", "date"], how="left")

    try:
        sw_l1_classify = fetch_sw_l1_classify(pro)
        sw_l1_members = fetch_sw_l1_membership_map(pro, sw_l1_classify, effective_trade_date)
        sw_l1_daily = fetch_sw_l1_daily(pro, sw_l1_classify, start_date, run_date)
        prepared = prepared.merge(sw_l1_members, on="ts_code", how="left")
        prepared = prepared.merge(
            sw_l1_daily[["sw_l1_code", "trade_date", "sw_l1_close", "sw_l1_ma20"]],
            on=["sw_l1_code", "trade_date"],
            how="left",
        )
        prepared["sw_l1_name"] = prepared["sw_l1_name_x"].combine_first(prepared["sw_l1_name_y"]) if "sw_l1_name_x" in prepared.columns else prepared["sw_l1_name"]
        prepared = prepared.drop(columns=[col for col in ["sw_l1_name_x", "sw_l1_name_y"] if col in prepared.columns])
    except Exception as exc:
        warnings.warn(f"industry data fetch failed; continue with missing values: {exc}")
        if "sw_l1_code" not in prepared.columns:
            prepared["sw_l1_code"] = pd.NA
        if "sw_l1_name" not in prepared.columns:
            prepared["sw_l1_name"] = pd.NA
        prepared["sw_l1_close"] = pd.NA
        prepared["sw_l1_ma20"] = pd.NA

    prepared = prepared[~prepared["ts_code"].astype(str).str.endswith(".BJ")].copy()
    prepared = prepared.sort_values(["ts_code", "date"]).reset_index(drop=True)
    prepared = ensure_required_prepared_columns(prepared)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(output_path, index=False, encoding="utf-8-sig")
    return {
        "requested_run_date": run_date,
        "effective_trade_date": effective_trade_date,
        "start_date": start_date,
        "row_count": int(len(prepared)),
        "output_file": str(output_path),
    }


def determine_effective_trade_date_from_csv(input_file: Path, run_date: str) -> str:
    run_date = normalize_date_str(run_date)
    df = pd.read_csv(input_file, usecols=["trade_date"], encoding="utf-8-sig", low_memory=False)
    dates = (
        df["trade_date"]
        .astype(str)
        .str.replace(r"\D", "", regex=True)
        .loc[lambda s: s.str.len() == 8]
    )
    valid = dates[dates <= run_date]
    if valid.empty:
        raise RuntimeError(f"no trade_date <= {run_date} found in {input_file}")
    return valid.max()
