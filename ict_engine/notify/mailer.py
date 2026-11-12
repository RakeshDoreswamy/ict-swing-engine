"""Email the daily list (Gmail SMTP with an App Password).

Settings come from a local ``.env`` file in the repo root, which git ignores (the repo is public):

    GMAIL_USER=you@gmail.com
    GMAIL_APP_PASSWORD=abcdefghijklmnop        # Google Account → Security → 2-Step → App passwords
    EMAIL_TO=a@gmail.com,b@gmail.com
    EMAIL_FROM_NAME=NSE ICT Screener           # optional

Never commit .env. Nothing here stores a password anywhere else.
"""
from __future__ import annotations

import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from ict_engine.config import ROOT


def load_env(path: Path | None = None) -> dict:
    p = path or ROOT / ".env"
    env = {}
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "EMAIL_TO", "EMAIL_FROM_NAME"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def build_message(subject: str, html: str, text: str, sender: str, to: list[str], inline: dict[str, Path],
                  attachments: list[Path], from_name: str = "NSE ICT Screener") -> EmailMessage:
    """``inline`` maps a content-id placeholder used in the HTML as cid:{key} to an image path."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, sender))
    msg["To"] = ", ".join(to)
    msg.set_content(text)
    cids = {k: make_msgid(domain="ict-swing-engine")[1:-1] for k in inline}
    for k, cid in cids.items():
        html = html.replace(f"cid:{k}", f"cid:{cid}")
    msg.add_alternative(html, subtype="html")
    related = msg.get_payload()[1]
    for k, path in inline.items():
        if Path(path).exists():
            related.add_related(Path(path).read_bytes(), "image", "png", cid=f"<{cids[k]}>")
    for a in attachments:
        if Path(a).exists():
            ctype = mimetypes.guess_type(str(a))[0] or "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            msg.add_attachment(Path(a).read_bytes(), maintype=maintype, subtype=subtype, filename=Path(a).name)
    return msg


def send(msg: EmailMessage, env: dict) -> None:
    user, pw = env.get("GMAIL_USER"), env.get("GMAIL_APP_PASSWORD")
    if not user or not pw:
        raise SystemExit("Email not sent: set GMAIL_USER and GMAIL_APP_PASSWORD in .env (see .env.example).")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
        s.login(user, pw.replace(" ", ""))
        s.send_message(msg)
