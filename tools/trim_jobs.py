#!/usr/bin/env python3
# 读 stdin 的 jobs JSON，按 JOB_FILTER 前缀过滤、JOB_LIMIT 截断，写回 jobs.json
import json
import os
import sys

raw = sys.stdin.read().strip()
data = json.loads(raw) if raw else {"jobs": []}
jobs = data.get("jobs", [])
flt = (os.environ.get("JOB_FILTER") or "").strip().strip("/")
if flt:
    jobs = [j for j in jobs if j == flt or j.startswith(flt)]
lim = (os.environ.get("JOB_LIMIT") or "").strip()
if lim.isdigit() and int(lim) > 0:
    jobs = jobs[: int(lim)]
print(f"待发 {len(jobs)} 个目录：{jobs}")
with open("jobs.json", "w") as f:
    json.dump(jobs, f, ensure_ascii=False)
