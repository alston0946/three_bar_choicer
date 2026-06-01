# Three Bar Daily Selector

这个仓库目录用于把 `3bar` 选股流程放到 GitHub Actions 里按工作日自动运行，并通过 QQ 邮箱发送每日结果。

## 当前实现

- 每个工作日 `17:00`（`Asia/Shanghai`）触发一次 GitHub Actions
- 运行时通过 `Tushare` 拉取最新数据，不提交大体积原始 CSV
- 生成当日 `three_bar_selection_candidates.csv`
- 发送“正文摘要 + CSV 附件”到指定邮箱
- 支持本地用现有 prepared CSV 做回归验证
- 当前选股口径中，启动 bar 和整理 bar 的上影线限制统一为 `2.2%`

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

## 输出文件

默认输出目录为 `artifacts/`，包含：

- `prepared_daily_data.csv`
  - 仅在 `Tushare` 模式下生成
- `three_bar_selection_candidates.csv`
- `mail_summary.json`

## 备注

- `industry_above_ma20` 口径为 `sw_l1_close >= sw_l1_ma20`
- 如果行业分类或行业指数当天获取失败，主选股仍会继续运行，只是行业相关字段为空
- 这个目录目前只是本地实现骨架；当前机器未发现可用 `git`，所以仓库初始化、提交和推送需要在你装好 `git` 的环境里完成
