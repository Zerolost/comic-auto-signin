#!/usr/bin/env python3
# 把目录里的图片按「文件名=配文」用 Markdown 消息发到 QQ 群：图文同条、交替排列
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.bot.qq.com"
EXT_CT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
          ".gif": "image/gif", ".webp": "image/webp"}
MAX_IMG = 10 * 1024 * 1024  # 素材库单张上限
PER_MSG = 5                 # 每条消息几张图
CONTENT_LIMIT = 3000        # 单条 markdown 文本保守上限


class HTTPFail(Exception):
    pass


def die(msg):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def http(method, path, token=None, body=None, raw=None, ctype="application/json", timeout=90):
    url = path if path.startswith("http") else API + path
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"QQBot {token}")
        req.add_header("X-Union-Appid", os.environ["QQ_APP_ID"])
    if data is not None:
        req.add_header("Content-Type", ctype)
    req.add_header("User-Agent", "qqbot-group-md-poster")
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


def call(*a, **k):
    # 关键步骤失败直接退出，避免半截消息
    try:
        return http(*a, **k)
    except HTTPFail as e:
        die(str(e))


def get_token():
    app_id = os.environ.get("QQ_APP_ID") or die("缺少 QQ_APP_ID")
    secret = os.environ.get("QQ_APP_SECRET") or die("缺少 QQ_APP_SECRET")
    r = call("POST", "/app/getAppAccessToken",
             body={"appId": app_id, "clientSecret": secret})
    return r.get("access_token") or die(f"取 access_token 失败：{r}")


def upload_media(token, path):
    """素材库三步上传，返回 qqbot-media:// 引用（平台转存，不依赖公网 URL）"""
    data = open(path, "rb").read()
    if len(data) > MAX_IMG:
        die(f"{os.path.basename(path)} 超过 10MB，素材库不收")
    name = os.path.basename(path)
    ct = EXT_CT[os.path.splitext(name)[1].lower()]
    md5 = hashlib.md5(data).hexdigest()
    prep = call("POST", "/v2/media-images/prepare", token, body={
        "file_name": name, "file_size": len(data), "content_type": ct,
        "md5": md5, "sha1": hashlib.sha1(data).hexdigest()})
    if not prep.get("presigned_url"):
        die(f"prepare 失败：{prep}")
    try:
        http("PUT", prep["presigned_url"], raw=data, ctype=ct)
    except HTTPFail as e:
        die(f"直传失败（Content-Type 需与 prepare 一致）：{e}")
    done = call("POST", "/v2/media-images/complete", token, body={
        "upload_id": prep["upload_id"], "md5": md5})
    return done.get("url") or die(f"complete 失败：{done}")


def send_markdown(token, gid, content, msg_id=None, seq=1):
    body = {"msg_type": 2, "markdown": {"content": content}}
    if msg_id:
        body["msg_id"] = msg_id
        body["msg_seq"] = seq
    r = call("POST", f"/v2/groups/{gid}/messages", token, body=body)
    if r.get("err_code") or r.get("code") not in (None, 0):
        die(f"发消息失败：{r}")
    return r


def pick_files(job):
    d = os.path.join(job, "images")
    if not os.path.isdir(d):
        return []
    return sorted((os.path.join(d, f) for f in os.listdir(d)
                   if os.path.splitext(f)[1].lower() in EXT_CT),
                  key=lambda p: os.path.basename(p))


def resolve_title(a, job):
    if a.title:
        return a.title
    tf = os.path.join(job, "text.md")
    if os.path.isfile(tf):
        lines = open(tf, encoding="utf-8").read().strip().splitlines()
        if lines and lines[0].strip():
            return lines[0].lstrip("# ").strip()
    return os.path.basename(job.rstrip("/"))

def list_media(token):
    """翻页拿全部素材，返回 (总数, [image_id...])"""
    ids, cursor = [], None
    while True:
        q = f"?cursor={urllib.parse.quote(cursor, safe='')}" if cursor else ""
        r = call("GET", "/v2/media-images" + q, token)
        ids += [i["image_id"] for i in (r.get("images") or [])]
        cursor = r.get("next_cursor")
        if not cursor:
            return r.get("total", len(ids)), ids


def cleanup_media(token, keep):
    """删掉最旧的素材直到剩余 keep 张；放不下就报错，避免发一半"""
    total, ids = list_media(token)
    print(f"素材库当前 {total} 张（上限 100，保留 {keep} 张）")
    if total <= keep:
        return 0
    drop = ids[len(ids) - (total - keep):]   # 列表按上传时间倒序，末尾最旧
    for iid in drop:
        call("DELETE", f"/v2/media-images/{iid}/delete", token)
    print(f"🧹 清理 {len(drop)} 张旧素材，剩余 {total - len(drop)} 张")
    return len(drop)


def reserve_for(need):
    """给本次要上传的图腾位置：上限 100，预留 QQ_MEDIA_RESERVE(默认 20) 张给别处"""
    try:
        reserve = int(os.environ.get("QQ_MEDIA_RESERVE", "20"))
    except ValueError:
        reserve = 20
    return max(1, 100 - reserve - need)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--title", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    gid = os.environ.get("QQ_GROUP_OPENID") or os.environ.get("QQ_GROUP_ID") \
        or die("缺少 QQ_GROUP_OPENID（群 OpenID，不是群号）")
    files = pick_files(a.job) or die(f"{a.job}/images 里没有图片（png/jpg/gif/webp）")
    title = resolve_title(a, a.job)

    if a.dry_run:
        print(f"# {title}\n")
        for i, p in enumerate(files, 1):
            stem = os.path.splitext(os.path.basename(p))[0]
            print(f"{i}. **{stem}**\n\n![{stem}](qqbot-media://image/v1/...)\n")
        return

    token = get_token()
    # 先把配额腾出来：留 5 张余量，其余按最旧删除
    cleanup_media(token, reserve_for(len(files)))

    n = 0
    while n < len(files):
        remaining = len(files) - n
        chunk = pick_chunk(files, n, title)
        # 上传前再确认一次空间（素材库是全机器人共享的）
        cleanup_media(token, reserve_for(len(chunk)))
        blocks = []
        for p in chunk:
            stem = os.path.splitext(os.path.basename(p))[0]
            url = upload_media(token, p)
            print(f"⬆️ {os.path.basename(p)}")
            blocks.append((stem, url))
        joined = ""
        for i, (stem, url) in enumerate(blocks, 1):
            first = stem.splitlines()[0][:60]
            joined += f"{n + i}. **{first}**\n\n![{first}]({url})\n\n"
        head = f"# {title}\n\n" if n == 0 else ""
        send_markdown(token, gid, (head + joined).rstrip())
        print(f"💬 已发送（第 {n + 1}-{n + len(chunk)} 张，共剩余 {remaining - len(chunk)} 张待发）")
        n += len(chunk)
        time.sleep(4)


def pick_chunk(files, n, title):
    """按张数和文本长度切一块"""
    chunk, content_len = [], len(title) + 40
    while n + len(chunk) < len(files) and len(chunk) < PER_MSG:
        stem = os.path.splitext(os.path.basename(files[n + len(chunk)]))[0]
        cost = len(stem) * 2 + 80
        if content_len + cost > CONTENT_LIMIT:
            break
        content_len += cost
        chunk.append(files[n + len(chunk)])
    return chunk


if __name__ == "__main__":
    main()
