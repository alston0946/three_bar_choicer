# Three Bar Daily Selector

这个仓库目录用于把 `3bar` 选股流程放到 GitHub Actions 里按工作日自动运行，并通过 QQ 邮箱发送每日结果。

## 当前实现

- 每个工作日 `17:00`（`Asia/Shanghai`）触发一次 GitHub Actions
- 运行时通过 `Tushare` 拉取最新数据，不提交大体积原始 CSV
- 生成当日 `three_bar_selection_candidates.csv`
- 发送“正文摘要 + CSV 附件”到指定邮箱
- 邮件发送独立为单独的 GitHub Actions 步骤，日志里会明确打印发送开始/成功状态
- 支持本地用现有 prepared CSV 做回归验证
- 当前选股口径中，启动 bar 和整理 bar 的上影线限制统一为 `2.2%`
  - 上影线比例口径为：`(high - max(open, close)) / max(open, close)`
- 本地运行时可以手动指定 `target_day/run-date` 做回测或补跑；GitHub Actions 不传日期参数，始终自动使用最新可拉到的有效交易日
- 当天手动或定时运行时，会优先使用 `Tushare` 实际可拉到的最新交易日数据，而不是只按交易日历硬推当天
- 如果运行时仍处于当天盘中或收盘后早段，默认会跳过“当天未稳定的日线”，自动改用上一个完整交易日

## 目录说明

- `run_daily_selection.py`
  - 每日入口脚本
- `tushare_data.py`
  - `Tushare` 取数、前复权、指标构建、行业与指数数据补齐
- `three_bar_selection_scan.py`
  - 选股逻辑本体，已改为显式输入/输出参数
- `send_email.py`
  - QQ SMTP 邮件发送
- `.github/workflows/daily-selection.yml`
  - GitHub Actions 工作流

## 依赖安装

```bash
python -m pip install -r requirements.txt
```

## 环境变量

本地运行或 GitHub Secrets 需要提供：

- `TUSHARE_TOKEN`
- `QQ_SMTP_SENDER`
- `QQ_SMTP_AUTH_CODE`
- `EMAIL_TO`
- 可选：`EMAIL_SUBJECT_PREFIX`

说明：

- `QQ_SMTP_SENDER` 是 QQ 发件邮箱地址
- `QQ_SMTP_AUTH_CODE` 不是邮箱登录密码，而是 QQ 邮箱 SMTP 授权码
- `EMAIL_TO` 可为单个邮箱，也可为逗号分隔的多个邮箱

## 本地回归验证

如果你想先不连 `Tushare`，直接用现有 prepared CSV 回归选股逻辑：

```bash
python run_daily_selection.py ^
  --run-date 20260508 ^
  --local-input-csv "..\\a_share_qfq_daily_20250101-20260430.csv" ^
  --output-dir artifacts
```

如果要走完整流程并发送邮件：

```bash
python run_daily_selection.py --run-date 20260530 --output-dir artifacts --send-email
```

如果你本地更习惯写 `target_day`，可以直接这样指定日期：

```bash
python run_daily_selection.py --target-day 20260530 --output-dir artifacts
```

如果要保留 `prepared_daily_data.csv` 方便调试：

```bash
python run_daily_selection.py --run-date 20260530 --output-dir artifacts --keep-prepared-data
```

如果你已经生成了 `mail_summary.json`，也可以单独发送邮件：

```bash
python send_email.py --summary-json artifacts/mail_summary.json --attachments artifacts/three_bar_selection_candidates.csv
```

## GitHub Secrets

在目标仓库的 `Settings -> Secrets and variables -> Actions` 中新增：

- `TUSHARE_TOKEN`
- `QQ_SMTP_SENDER`
- `QQ_SMTP_AUTH_CODE`
- `EMAIL_TO`
- 可选：`EMAIL_SUBJECT_PREFIX`

## GitHub Actions 定时

工作流使用 UTC cron：

- `0 9 * * 1-5`

对应上海时间：

- 每周一到周五 `17:00`

注意：

- GitHub Actions 的 `schedule` 是 best effort，不保证一定在 `17:00:00` 准点触发
- 如果你希望“尽量在 17 点前收到”，可以把 cron 再提前一些
- 日志里会同时打印 `requested_run_date`、`calendar_last_trade_date`、`data_last_trade_date`、`effective_trade_date`、`skipped_same_day_fetch`
- 当前 GitHub Actions 默认不传 `--run-date` 或 `--target-day`，因此会始终按运行当天去追最新可用交易日

## 输出文件

默认输出目录为 `artifacts/`，包含：

- `three_bar_selection_candidates.csv`
- `mail_summary.json`

可选输出：

- `prepared_daily_data.csv`
  - 仅在 `Tushare` 模式下且传入 `--keep-prepared-data` 时生成

GitHub Actions 默认只上传：

- `three_bar_selection_candidates.csv`
- `mail_summary.json`

## 备注

- `industry_above_ma20` 口径为 `sw_l1_close >= sw_l1_ma20`
- 如果行业分类或行业指数当天获取失败，主选股仍会继续运行，只是行业相关字段为空
- 当前工作流增加了 `concurrency` 配置，避免这个仓库自己的手动触发和定时触发相互重叠
