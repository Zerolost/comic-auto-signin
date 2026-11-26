#!/usr/bin/env python3
# 把一个 job 目录里的 text.md + images/* 合成一封内嵌多图的 HTML 邮件，发到 QQ 邮箱
import argparse
import base64
import glob
import html
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MIME = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".gif": "gif",
        ".webp": "webp", ".bmp": "bmp"}
MAX_TOTAL = 23 * 1024 * 1024  # QQ 邮箱单封上限约 25MB


def env(name, default=None, required=False):
    v = os.environ.get(name) or default
    if required and not v:
        sys.exit(f"缺少环境变量 {name}")
    return v


def md_to_html(text):
    # 只支持够用的子集：标题、粗体、行内代码、链接、列表、代码块、图片语法（忽略）
    lines = text.splitlines()
    out, in_code = [], False
    for raw in lines:
        line = raw.rstrip()
        if line.strip().startswith("```"):
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        esc = html.escape(line)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
        esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
        esc = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
                     r'<a href="\2">\1</a>', esc)
        if re.match(r"^#{1,6}\s", line):
            out.append(f"<h3>{esc.lstrip('# ').strip()}</h3>")
        elif re.match(r"^\s*[-*]\s+", line):
            out.append(f"<li>{esc.lstrip('-* ').strip()}</li>")
        elif esc.strip() == "":
            out.append("<br>")
        else:
            out.append(f"<p>{esc}</p>")
    if in_code:
        out.append("</pre>")
    body = "\n".join(out)
    body = re.sub(r"(?:<li>.*?</li>\n?)+", lambda m: "<ul>" + m.group(0) + "</ul>", body)
    return body


def collect_images(images_dir, manifest=None):
    files = []
    if manifest and os.path.isfile(manifest):
        for line in open(manifest, encoding="utf-8"):
            p = line.strip()
            if p and not p.startswith("#"):
                files.append(os.path.join(images_dir, p) if not os.path.isabs(p) else p)
    else:
        files = [f for f in glob.glob(os.path.join(images_dir, "*"))
                 if os.path.splitext(f)[1].lower() in IMG_EXT]
        files.sort(key=lambda p: os.path.basename(p))
    return [f for f in files if os.path.isfile(f)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True, help="job 目录（含 text.md / images/）")
    ap.add_argument("--subject", default=None)
    ap.add_argument("--to", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    user = env("QQMAIL_USER", required=True)
    pwd = env("QQMAIL_AUTH_CODE", required=True)
    to = a.to or env("QQMAIL_TO", user)
    host = env("QQMAIL_SMTP_HOST", "smtp.qq.com")
    port = int(env("QQMAIL_SMTP_PORT", "465"))
    max_per_mail = int(env("MAX_IMAGES", "20"))

    text_path = os.path.join(a.job, "text.md")
    text = open(text_path, encoding="utf-8").read().strip() if os.path.isfile(text_path) else ""
    images = collect_images(os.path.join(a.job, "images"),
                            os.path.join(a.job, "images.txt"))
    if not text and not images:
        sys.exit(f"job {a.job} 里没有 text.md 也没有图片")
    if not text:
        text = f"（{os.path.basename(a.job.rstrip('/'))}）"

    subject = a.subject or os.path.basename(a.job.rstrip("/"))
    title_line = html.escape(text.splitlines()[0])[:120]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg["X-Priority"] = "3"
    msg.set_content(text + "\n\n" + "\n".join(os.path.basename(p) for p in images))

    counter = [0]
    total = [0]

    def attach_html(chunk_idx, chunk):
        pieces = []
        for i, p in enumerate(chunk):
            ext = os.path.splitext(p)[1].lower()
            with open(p, "rb") as f:
                data = f.read()
            if total[0] + len(data) > MAX_TOTAL:
                pieces.append("<p><i>⚠ 剩余图片超出单封大小上限，已跳过</i></p>")
                print(f"跳过（体积超限）：{p}", file=sys.stderr)
                continue
            total[0] += len(data)
            counter[0] += 1
            cid = f"img{counter[0]}@{abs(hash(p)) % 10**8}.qqmail"
            pieces.append(f'<div style="margin:14px 0"><img src="cid:{cid}" '
                          f'style="max-width:100%;border-radius:8px" alt="{html.escape(os.path.basename(p))}"></div>')
            msg.add_related(data, maintype="image", subtype=MIME.get(ext, "png"),
                            cid=f"<{cid}>", filename=os.path.basename(p))
        head = ""
        if chunk_idx == 0:
            head = f"<h2>{html.escape(subject)}</h2>{md_to_html(text)}<hr>"
        else:
            head = f"<p><i>{html.escape(subject)}（续 {chunk_idx + 1}）</i></p><hr>"
        foot = "<hr><p style='color:#999;font-size:12px'>由 GitHub Actions 发送 · " \
               f"{len(chunk)} 张图 · {formatdate(localtime=True)[-14:]}</p>"
        body = ("<html><body style=\"font-family:-apple-system,Segoe UI,sans-serif;"
                "font-size:15px;line-height:1.6\">" + head + "".join(pieces) + foot + "</body></html>")
        msg.add_alternative(body, subtype="html")

    attach_html(0, images[:max_per_mail] if max_per_mail > 0 else images)

    if a.dry_run:
        print(f"[dry-run] subject={subject} to={to} images={counter[0]} bytes={total[0]}")
        return

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
        s.login(user, pwd)
        s.send_message(msg)
    print(f"✅ 已发送 {counter[0]} 张图 → {to}（{subject}）")


if __name__ == "__main__":
    main()
