#!/usr/bin/env python3
# 本地自测：伪造一台 QQ 机器人服务端，把发送流程全跑一遍
import base64
import http.server
import json
import os
import subprocess
import sys
import threading

CALLS = []


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_POST(self):
        body = self._body()
        path = self.path
        CALLS.append((self.command, path, body[:200]))
        if not self.headers.get("Authorization", "").startswith("QQBot ") and path != "/app/getAppAccessToken":
            return self._json({"code": 401, "message": "no token"}, 401)
        if path == "/app/getAppAccessToken":
            return self._json({"access_token": "FAKE", "expires_in": "7200"})
        if path.endswith("/upload_prepare"):
            d = json.loads(body)
            assert d["file_size"].isdigit() and len(d["md5"]) == 32 and len(d["md5_10m"]) == 32
            return self._json({"upload_id": "up1", "block_size": "5242880",
                               "parts": [{"index": 0, "presigned_url": "http://127.0.0.1:%d/put" % PORT,
                                          "block_size": "5242880"}]})
        if path.endswith("/upload_part_finish"):
            return self._json({})
        if path.endswith("/files"):
            d = json.loads(body)
            if "file_data" in d:
                assert base64.b64decode(d["file_data"])[:4] == b"\x89PNG", "直传数据应可 base64 还原"
            if "upload_id" in d:
                assert d["upload_id"] == "up1"
            return self._json({"file_info": "INFO_" + d.get("file_name", "?"), "ttl": 0})
        if path.endswith("/messages"):
            d = json.loads(body)
            assert d["msg_type"] in (0, 7)
            if d["msg_type"] == 0:
                assert d["content"] and len(d["content"]) <= 200
            else:
                assert d["media"]["file_info"].startswith("INFO_")
            return self._json({"id": "msg_1", "timestamp": "now"})
        return self._json({"code": 404}, 404)

    def do_PUT(self):
        CALLS.append((self.command, self.path, len(self._body())))
        self.send_response(200)
        self.end_headers()

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


PORT = 18731
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

os.environ.update({"QQ_APP_ID": "1", "QQ_APP_SECRET": "s", "QQ_GROUP_OPENID": "GID"})

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import qqbot_group_send as q

q.API = f"http://127.0.0.1:{PORT}"

# 造 1 张小图 + 1 张大图（触发分片），测试文件名即标题
import struct
import zlib


def png(w, h, c):
    raw = b"".join(b"\x00" + bytes(c) * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw, 0)) + ch(b"IEND", b"")


job = "/tmp/qqjob"
os.makedirs(job + "/images", exist_ok=True)
open(job + "/images/第一张.png", "wb").write(png(40, 30, (10, 200, 90)))
# 5MB+ 噪声图片会不合法，改用大尺寸未压缩 PNG
open(job + "/images/大图.png", "wb").write(png(1400, 1400, (200, 30, 30)))
print("大图大小", os.path.getsize(job + "/images/大图.png"))

sys.argv = ["x", "--job", job]
q.main()
print("调用序列：", [c[0] + " " + c[1].split("/")[-1] for c in CALLS])
print("PASS")
