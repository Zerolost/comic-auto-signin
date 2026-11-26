#!/usr/bin/env python3
# 列出 repo 里 jobs/ 下待发的 job；可只挑 jobs/<id> 前缀
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://api.github.com"


def api(path, method="GET", body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "qq-mail-job",
            "Content-Type": "application/json",
        })
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    prefix = (sys.argv[1] if len(sys.argv) > 1 else "").strip().strip("/")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    out = []
    try:
        listing = api(f"/repos/{repo}/contents/jobs?ref={urllib.parse.quote(branch)}")
    except Exception as e:
        print(f"jobs/ 目录读取失败：{e}", file=sys.stderr)
        listing = []
    for item in listing or []:
        if item.get("type") != "dir":
            continue
        name = item["name"]
        if name.startswith(".") or name.startswith("_"):
            continue
        if prefix and not (name == prefix or name.startswith(prefix)):
            continue
        has = set()
        try:
            for f in api(f"/repos/{repo}/contents/jobs/{name}") or []:
                has.add(f["name"])
        except Exception:
            pass
        if not ({"text.md", "images.txt"} & has) and not has:
            continue
        out.append(name)
    jobs = sorted(out)
    print(f"jobs/ 下待发 {len(jobs)} 个：{jobs}", file=sys.stderr)
    print(json.dumps(jobs, ensure_ascii=False))


if __name__ == "__main__":
    main()
