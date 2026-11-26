// QQ 群 openid 抓取器：订阅 QQ 机器人事件，把 group_openid 打到日志里
// 只需要部署一次，抓到值后可以删掉

const TOKEN_CACHE = { key: "", token: "", exp: 0 }

async function accessToken(env) {
  const key = env.QQ_APP_ID + ":" + env.QQ_APP_SECRET
  if (TOKEN_CACHE.key === key && Date.now() < TOKEN_CACHE.exp) return TOKEN_CACHE.token
  const r = await fetch("https://api.bot.qq.com/app/getAppAccessToken", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ appId: env.QQ_APP_ID, clientSecret: env.QQ_APP_SECRET }),
  })
  const d = await r.json()
  if (!d.access_token) throw new Error("getAppAccessToken 失败: " + JSON.stringify(d))
  TOKEN_CACHE.key = key
  TOKEN_CACHE.token = d.access_token
  TOKEN_CACHE.exp = Date.now() + (Number(d.expires_in || 7200) - 120) * 1000
  return TOKEN_CACHE.token
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url)

    // 健康检查 / 手动查看最近抓到的东西
    if (url.pathname === "/") {
      return new Response("ok", { headers: { "content-type": "text/plain" } })
    }

    if (req.method !== "POST") return new Response("method not allowed", { status: 405 })

    // QQ 平台要求 60 秒内回 200，先把 body 收完
    const raw = await req.text()
    let ev = null
    try {
      ev = JSON.parse(raw)
    } catch {
      return new Response("bad json", { status: 400 })
    }

    const t = ev.t || ev.event_type || "unknown"
    const d = ev.d || {}
    const gid = d.group_openid || d.group_id || d.openid
    console.log("EVENT", t, "op=", ev.op, "raw=", raw.slice(0, 1500))

    // 转发给管理员：把原始事件发回给 bot 管理员单聊，手机上直接能看到
    if (env.ADMIN_USER_OPENID) {
      try {
        const token = await accessToken(env)
        const label = gid ? `群 openid:\n${gid}` : `事件 ${t}（无 group_openid）`
        await fetch(`https://api.bot.qq.com/v2/users/${env.ADMIN_USER_OPENID}/messages`, {
          method: "POST",
          headers: {
            Authorization: "QQBot " + token,
            "X-Union-Appid": env.QQ_APP_ID,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ msg_type: 0, content: label.slice(0, 900) }),
        })
      } catch (e) {
        console.log("转发失败", String(e))
      }
    }

    // 回 op 12 表示收到（无参回调）
    if (ev.op === 13) {
      return Response.json({ op: 12, d: { plain_token: d.plain_token, signature: "" } })
    }
    return new Response("", { status: 200 })
  },
}
