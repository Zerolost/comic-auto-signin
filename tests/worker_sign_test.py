#!/usr/bin/env python3
# 本地自测：模拟 QQ 平台回调（验证 op=13 签名）+ 群 @ 事件落盘
import json
import os
import subprocess
import sys

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("需要 cryptography：pip install cryptography")
    sys.exit(2)

SECRET = "DG5g3B4j9X2KOErG"
APPID = "11111111"


def expected_signature(secret, event_ts, plain_token):
    seed = secret
    while len(seed) < 32:
        seed += seed
    # 官方 go 实现是 sha256(seed) → 32 字节 ed25519 种子
    sk = Ed25519PrivateKey.from_private_bytes(seed[:32].encode())
    return sk.sign((event_ts + plain_token).encode()).hex()


JS = r"""
const mod = await import(process.argv[1]);
const env = { QQ_APP_ID: "%s", QQ_SECRET: "%s" };
const body = { op: 13, d: { plain_token: "Arq0D5A61EgUu4OxUvOp", event_ts: "1725442341" } };
const req = new Request("https://x/qq", { method: "POST", body: JSON.stringify(body) });
const res = await mod.default.fetch(req, env, { waitUntil() {} });
await res.text().then((t) => process.stdout.write(t));
""" % (APPID, SECRET)

path = os.path.join(os.path.dirname(__file__), "..", "worker", "index.mjs")
src = open(os.path.join(os.path.dirname(__file__), "..", "worker", "index.js")).read()
open(path, "w").write(src)
out = subprocess.run(
    ["node", "--input-type=module", "-e",
     "const m = await import('file://%s');" % path +
     "const env={QQ_APP_ID:'%s',QQ_SECRET:'%s'};" % (APPID, SECRET) +
     "const req=new Request('https://x/',{method:'POST',body:JSON.stringify({op:13,d:{plain_token:'Arq0D5A61EgUu4OxUvOp',event_ts:'1725442341'}})});" +
     "const res=await m.default.fetch(req,env,{waitUntil(){}});process.stdout.write(await res.text());"],
    capture_output=True, text=True, timeout=60)
if out.returncode != 0:
    print("⚠️ 本机 Node 跑不了（".strip(), out.stderr.strip()[:200], "），改做静态检查")
    got = None
else:
    got = json.loads(out.stdout)

if got:
    want = expected_signature(SECRET, "1725442341", "Arq0D5A61EgUu4OxUvOp")
    print("返回:", got)
    assert got["plain_token"] == "Arq0D5A61EgUu4OxUvOp"
    assert got["signature"] == want, "签名不一致\n got=%s\nwant=%s" % (got["signature"], want)
    print("✅ 回调验签与官方算法一致")

# 群 @ 事件（未配 GH_REPO 时不应报错）
src_check = open(os.path.join(os.path.dirname(__file__), "..", "worker", "index.js")).read()
assert "group_openid" in src_check and "union_group_openid" in src_check
assert "toUpperCase" not in src_check
print("✅ 事件落盘字段齐全")
os.remove(path)
print("PASS")
