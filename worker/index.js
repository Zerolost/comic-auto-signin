// QQ 机器人事件抓取器：收到群 @ 消息就把 group_openid 记下来，供 Actions 自动读取
const enc = new TextEncoder();



// 官方做法 seed 是「secret 自身重复到 ≥32 字符后取前 32 个字符」，不是哈希
async function seedFor(secret) {
  let seed = secret;
  while (seed.length < 32) seed += seed;
  return seed.slice(0, 32);
}

function hex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// 用 secret 派生 ed25519 私钥做签名（供开放平台校验回调地址）
async function sign(secret, msg) {
  const seed = await seedFor(secret);
  // 统一用 PKCS#8 包裹 32 字节种子，Workers 与 Node webcrypto 都支持
  const pkcs8 = new Uint8Array(48);
  pkcs8.set([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20]);
  pkcs8.set(enc.encode(seed), 16);
  const key = await crypto.subtle.importKey("pkcs8", pkcs8, { name: "Ed25519" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("Ed25519", key, enc.encode(msg)));
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function gh(repo, file, token, method = "GET", body) {
  const url = `https://api.github.com/repos/${repo}/contents/${file}`;
  const r = await fetch(url, {
    method,
    headers: {
      authorization: `Bearer ${token}`,
      accept: "application/vnd.github+json",
      "user-agent": "qqbot-openid-catcher",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 404) return { missing: true };
  const j = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data: j };
}

async function save(env, obj) {
  if (!env.GH_REPO || !env.GH_TOKEN) return;
  const path = env.STATE_FILE || "state/group_openid.json";
  const cur = await gh(env.GH_REPO, path, env.GH_TOKEN);
  const sha = cur.data && cur.data.sha;
  const content = btoa(unescape(encodeURIComponent(JSON.stringify(obj, null, 2))));
  await gh(env.GH_REPO, path, env.GH_TOKEN, "PUT", {
    message: `chore(state): 记录 ${obj.group_openid || "未知"} 群 openid`,
    content,
    ...(sha ? { sha } : {}),
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "GET") {
      return json({ ok: true, appid: env.QQ_APP_ID || null, now: new Date().toISOString() });
    }
    const raw = await request.text();
    let body = {};
    try {
      body = JSON.parse(raw);
    } catch {
      return json({ ok: false, error: "bad json" }, 400);
    }
    const op = body.op;
    const d = body.d || {};
    // 回调地址验证
    if (op === 13 && d.plain_token) {
      const signature = await sign(env.QQ_SECRET || "", (d.event_ts || "") + d.plain_token);
      return json({ plain_token: d.plain_token, signature });
    }
    // 其余事件：把群 openid 记到仓库（含 union_group_openid，跨 bot 可用）
    const gid = d.group_openid;
    if (gid) {
      const state = {
        group_openid: gid,
        union_group_openid: d.union_group_openid || null,
        appid: env.QQ_APP_ID || null,
        from_openid: (d.author && d.author.member_openid) || null,
        event: body.t || null,
        saved_at: new Date().toISOString(),
      };
      ctx.waitUntil(save(env, state));
      return json({ ok: true, saved: true });
    }
    if (op === 0 && body.t) {
      return json({ ok: true, ignored: body.t });
    }
    return json({ ok: true });
  },
};
