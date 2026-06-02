# -*- coding: utf-8 -*-

import argparse
import json
import os
import smtplib
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send the daily 3-bar selection summary email.")
    parser.add_argument("--summary-json", required=True, help="Path to mail_summary.json.")
    parser.add_argument("--attachments", nargs="*", default=[], help="Attachment file paths.")
    return parser.parse_args()


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


def build_email_subject(summary: dict) -> str:
    prefix = os.getenv("EMAIL_SUBJECT_PREFIX", "").strip()
    subject = f"3bar每日选股 {summary['effective_trade_date']} 候选{summary['candidate_count']}只"
    return f"{prefix} {subject}".strip() if prefix else subject


def mask_email_address(email: str) -> str:
    email = str(email).strip()
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "***"
    else:
        masked_local = local[:2] + "***" + local[-1:]
    return f"{masked_local}@{domain}"


def load_summary(summary_json: Path) -> dict:
    return json.loads(summary_json.read_text(encoding="utf-8"))


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

    missing_attachments = [str(path) for path in attachments if not path.exists()]
    if missing_attachments:
        raise FileNotFoundError(f"attachment file missing: {missing_attachments}")

    print(f"email_subject={subject}")
    print(f"email_sender={mask_email_address(sender)}")
    print(f"email_receivers={','.join(mask_email_address(item) for item in receivers)}")
    print(f"email_attachment_count={len(attachments)}")
    if attachments:
        print(f"email_attachments={','.join(path.name for path in attachments)}")
    print(f"email_smtp_host={SMTP_HOST}")
    print(f"email_send_start=True")

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

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.login(sender, auth_code)
        print("email_login_success=True")
        server.sendmail(sender, receivers, msg.as_string())
        print("email_send_success=True")


def main() -> None:
    args = parse_args()
    summary_path = Path(args.summary_json)
    attachments = [Path(item) for item in args.attachments]
    summary = load_summary(summary_path)
    body = build_summary_body(summary)
    subject = build_email_subject(summary)
    send_email(subject=subject, body=body, attachments=attachments)


if __name__ == "__main__":
    main()
