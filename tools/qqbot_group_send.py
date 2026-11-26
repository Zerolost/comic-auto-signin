#!/usr/bin/env python3
# 用 QQ 官方机器人 OpenAPI 把图片发到指定群：文件名(去后缀) 当文字，紧随其后发图片
import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.bot.qq.com"
IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp"}
DIRECT_LIMIT = 5 * 1024 * 1024  # 二进制直传上限



class HTTPFail(Exception):
    pass


def die(msg):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def http(method, path, token=None, body=None, raw=None, ctype="application/json", timeout=60):
    url = path if path.startswith("http") else API + path
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"QQBot {token}")
        req.add_header("X-Union-Appid", os.environ["QQ_APP_ID"])
    if data is not None:
        req.add_header("Content-Type", ctype)
    req.add_header("User-Agent", "qq-group-image-poster")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        raise HTTPFail(f"{method} {path} HTTP {e.code}: {txt[:300]}")
    try:
        return json.loads(txt) if txt.strip() else {}
    except json.JSONDecodeError:
        return {"raw": txt}


def get_token():
    app_id = os.environ.get("QQ_APP_ID") or die("缺少 QQ_APP_ID")
    secret = os.environ.get("QQ_APP_SECRET") or die("缺少 QQ_APP_SECRET")
    r = http("POST", "/app/getAppAccessToken",
             body={"appId": app_id, "clientSecret": secret})
    tok = r.get("access_token") or die(f"取 access_token 失败：{r}")
    return tok


def upload_image(token, gid, path):
    name = os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read()
    if len(data) <= DIRECT_LIMIT:
        try:
            r = http("POST", f"/v2/groups/{gid}/files", token, body={
                "file_type": 1, "srv_send_msg": False,
                "file_name": name, "file_data": base64.b64encode(data).decode()})
            if r.get("file_info"):
                return r["file_info"]
            print(f"  · 直传无 file_info，转分片：{r}", file=sys.stderr)
        except SystemExit:
            print("  · 直传失败，转分片", file=sys.stderr)
    # 分片上传：prepare → PUT → part_finish → files 合并
    md5 = hashlib.md5(data).hexdigest()
    r = http("POST", f"/v2/groups/{gid}/upload_prepare", token, body={
        "file_type": 1, "file_size": str(len(data)), "file_name": name,
        "md5": md5, "sha1": hashlib.sha1(data).hexdigest(),
        "md5_10m": hashlib.md5(data[:10002432]).hexdigest()})
    upload_id, parts = r.get("upload_id"), r.get("parts") or []
    if not upload_id or not parts:
        die(f"upload_prepare 返回异常：{str(r)[:300]}")
    for p in parts:
        idx = p["index"]
        size = int(p.get("block_size") or r.get("block_size"))
        start = sum(int(x.get("block_size") or r.get("block_size")) for x in parts if x["index"] < idx)
        chunk = data[start:start + size]
        last = None
        for attempt in range(3):
            try:
                http("PUT", p["presigned_url"], raw=chunk, ctype="application/octet-stream")
                last = None
                break
            except HTTPFail as e:
                last = e
                time.sleep(1 + attempt)
        if last is not None:
            die(f"分片 {idx} 上传失败：{last}")
        http("POST", f"/v2/groups/{gid}/upload_part_finish", token, body={
            "upload_id": upload_id, "part_index": idx,
            "block_size": str(len(chunk)), "md5": hashlib.md5(chunk).hexdigest()})
    r = http("POST", f"/v2/groups/{gid}/files", token, body={
        "file_type": 1, "srv_send_msg": False,
        "file_name": name, "upload_id": upload_id})
    info = r.get("file_info") or die(f"合并失败：{str(r)[:300]}")
    return info


def send_text(token, gid, content, msg_id=None, seq=1):
    body = {"msg_type": 0, "content": content}
    return _send(token, gid, body, msg_id, seq)


def send_image(token, gid, file_info, msg_id=None, seq=1):
    body = {"msg_type": 7, "media": {"file_info": file_info}}
    return _send(token, gid, body, msg_id, seq)


def _send(token, gid, body, msg_id, seq):
    if msg_id:
        body["msg_id"] = msg_id
        body["msg_seq"] = seq
    r = http("POST", f"/v2/groups/{gid}/messages", token, body=body)
    if r.get("id") or r.get("code") in (0, None) and "err_code" not in r:
        return r
    die(f"发消息失败：{str(r)[:300]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--title", default=None, help="覆盖默认标题（配文）")
    ap.add_argument("--reply", default=None, help="被动回复用的 msg_id")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    gid = os.environ.get("QQ_GROUP_OPENID") or os.environ.get("QQ_GROUP_ID") \
        or die("缺少 QQ_GROUP_OPENID（群 OpenID，不是群号）")
    imgs_dir = os.path.join(a.job, "images")
    files = sorted((os.path.join(imgs_dir, f) for f in os.listdir(imgs_dir)
                    if os.path.splitext(f)[1].lower() in IMG_EXT),
                   key=lambda p: os.path.basename(p)) if os.path.isdir(imgs_dir) else []
    if not files:
        die(f"{imgs_dir} 里没有图片（支持 png/jpg/bmp）")
    caption = a.title or os.path.basename(a.job.rstrip("/"))
    text_file = os.path.join(a.job, "text.md")
    if not a.title and os.path.isfile(text_file):
        first = open(text_file, encoding="utf-8").read().strip().splitlines()
        if first and first[0].strip():
            caption = first[0].lstrip("# ").strip()

    plan = []
    for i, p in enumerate(files):
        stem = os.path.splitext(os.path.basename(p))[0]
        if i == 0 and not a.reply:
            plan.append(("text", caption))
            if caption != stem:
                plan.append(("text", stem))
        else:
            plan.append(("text", stem if stem else caption))
        plan.append(("image", p))

    if a.dry_run:
        print(json.dumps([(k, v if k == "text" else os.path.basename(v)) for k, v in plan],
                         ensure_ascii=False, indent=1))
        return

    token = get_token()
    for i, (kind, val) in enumerate(plan):
        msg_id = a.reply if i == 0 else None
        if kind == "text":
            send_text(token, gid, val, msg_id)
            print(f"💬 {val}")
        else:
            info = upload_image(token, gid, val)
            send_image(token, gid, info, msg_id)
            print(f"🖼 {os.path.basename(val)}")
        time.sleep(1.2)


if __name__ == "__main__":
    main()
