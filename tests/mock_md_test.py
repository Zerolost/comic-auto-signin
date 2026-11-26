#!/usr/bin/env python3
# 本地自测：伪造 QQ 机器人服务端 + COS，跑通 Markdown 图文同发流程
import http.server
import json
import os
import subprocess
import sys
import threading
import urllib.parse

CALLS = []
STORE = {}
WIDTH = 1200  # QQ Markdown 里图片允许的最大字节数（这里用保守值）

import struct
import zlib


def png(w, h, c):
    raw = b"".join(b"\x00" + bytes(c) * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw, 9)) + ch(b"IEND", b"")


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        CALLS.append(("POST", self.path))
        path = urllib.parse.urlparse(self.path).path
        if not self.headers.get("Authorization", "").startswith("QQBot ") and path != "/app/getAppAccessToken":
            return self._json({"code": 401}, 401)
        d = json.loads(raw) if raw else {}
        if path == "/app/getAppAccessToken":
            assert d["appId"] and d["clientSecret"]
            return self._json({"access_token": "FAKE", "expires_in": "7200"})
        if path == "/v2/media-images/prepare":
            assert d["content_type"] == "image/png" and d["file_name"].endswith(".png")
            assert len(d["md5"]) == 32 and len(d["sha1"]) == 40 and d["file_size"] > 0
            uid = "up%d" % len(STORE)
            STORE[uid] = {"name": d["file_name"], "size": d["file_size"], "put": False}
            return self._json({"upload_id": uid, "presigned_url":
                               f"http://127.0.0.1:{PORT}/cos/{uid}", "expires_in": 3600})
        if path == "/v2/media-images/complete":
            assert d["upload_id"] in STORE and STORE[d["upload_id"]]["put"], "complete 前必须有 PUT"
            return self._json({"image_id": "img_" + d["upload_id"],
                               "url": "qqbot-media://image/v1/" + d["upload_id"], "ttl": 7776000})
        if path.endswith("/messages"):
            assert d["msg_type"] == 2 and d["markdown"]["content"]
            c = d["markdown"]["content"]
            assert "qqbot-media://image/v1/" in c, "图片应走平台引用"
            assert "http" not in c, "不应出现公网链接"
            assert len(c.encode()) <= 4000
            return self._json({"id": "msg_ok", "timestamp": "now"})
        return self._json({"code": 404}, 404)

    def do_PUT(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        CALLS.append(("PUT", self.path, n))
        uid = self.path.rsplit("/", 1)[-1]
        if uid in STORE:
            STORE[uid]["put"] = True
        assert self.headers.get("Content-Type") == "image/png", self.headers.get("Content-Type")
        assert body[:4] == b"\x89PNG", "PUT 必须是 png 二进制"
        self.send_response(200)
        self.end_headers()


PORT = 18733
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

os.environ.update({"QQ_APP_ID": "1", "QQ_APP_SECRET": "s", "QQ_GROUP_OPENID": "GID"})
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import qqbot_md_send as q

q.API = f"http://127.0.0.1:{PORT}"

job = "/tmp/qqmd"
os.makedirs(job + "/images", exist_ok=True)
for name, color in [("1.猫咖.png", (10, 120, 90)), ("2.新开的店.png", (200, 60, 30)),
                    ("3.小图.png", (30, 30, 200))]:
    open(job + "/images/" + name, "wb").write(png(20, 20, color))
open(job + "/text.md", "w").write("# 本周集合\n\n其他说明\n")

sys.argv = ["x", "--job", job]
q.main()
print("调用序列：", [c[0] + " " + c[1].split("/")[-1] for c in CALLS])
print("PASS")
