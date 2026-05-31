# -*- coding: utf-8 -*-

import os
import smtplib
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465


def build_summary_body(summary: dict) -> str:
    lines = [
        f"运行日期: {summary.get('requested_run_date', '')}",
        f"生效交易日: {summary.get('effective_trade_date', '')}",
        f"候选数量: {summary.get('candidate_count', 0)}",
        "",
        "一级行业 MA20 统计:",
    ]

    industry_counts = summary.get("industry_above_ma20_counts", {})
    if industry_counts:
        for key, value in industry_counts.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- 无")

    lines.append("")
    lines.append("前20条候选:")
    top_rows = summary.get("top_candidates", [])
    if not top_rows:
        lines.append("- 当日无候选")
    else:
        header = f"{'ticker':<8} {'name':<10} {'setup':<10} {'board':<6} {'ignite_pct':>10} {'industry_ma20':>14}"
        lines.append(header)
        lines.append("-" * len(header))
        for row in top_rows:
            lines.append(
                f"{str(row.get('ticker', '')):<8} "
                f"{str(row.get('name', ''))[:10]:<10} "
                f"{str(row.get('setup_type', ''))[:10]:<10} "
                f"{str(row.get('board_type', '')):<6} "
                f"{str(row.get('ignite_pct_chg_pct', '')):>10} "
                f"{str(row.get('industry_above_ma20', '')):>14}"
            )
    return "\n".join(lines)


def send_email(subject: str, body: str, attachments: list[Path]) -> None:
    sender = os.getenv("QQ_SMTP_SENDER", "").strip()
    auth_code = os.getenv("QQ_SMTP_AUTH_CODE", "").strip()
    receiver_raw = os.getenv("EMAIL_TO", "").strip()
    if not sender:
        raise RuntimeError("QQ_SMTP_SENDER is required")
    if not auth_code:
        raise RuntimeError("QQ_SMTP_AUTH_CODE is required")
    if not receiver_raw:
        raise RuntimeError("EMAIL_TO is required")

    receivers = [item.strip() for item in receiver_raw.split(",") if item.strip()]
    if not receivers:
        raise RuntimeError("EMAIL_TO is empty after parsing")

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(receivers)
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for attachment in attachments:
        with attachment.open("rb") as fh:
            part = MIMEApplication(fh.read(), Name=attachment.name)
        part["Content-Disposition"] = f'attachment; filename="{attachment.name}"'
        msg.attach(part)

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(sender, auth_code)
        server.sendmail(sender, receivers, msg.as_string())
