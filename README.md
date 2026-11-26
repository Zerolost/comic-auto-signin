# QQ 群发图

在 GitHub 上**点按钮**，把**私有仓库**里的图片 + 文字发到指定 QQ 群（QQ 官方机器人）。

## 用法

```
jobs/
└─ 20261126-晚点吃啥/        ← 目录名 = 第一条配文（也可用 text.md 首行覆盖）
   ├─ text.md                ← 可选
   ├─ images.txt             ← 可选，指定发送顺序（一行一个文件名）
   └─ images/
      ├─ 1.猫咖.png
      └─ 2.新开的店.jpeg
```

实际发到群里是一条 **Markdown 消息**，图文交替：

```
# 20261126-晚点吃啥
1. **1.猫咖**
   🖼 1.猫咖.png
2. **2.新开的店**
   🖼 2.新开的店.jpeg
```

- 配文取 `text.md` 首行，没有就用目录名
- 每张图的配文 = 文件名（去后缀）
- 一条消息最多 5 张，多了自动拆成下一条（防单条超长 / 触发频控）

1. 把图传到 `jobs/<目录名>/images/`
2. Actions → **QQ 群发图** → Run workflow
   - `job` 留空 = 发全部待发；填前缀只发匹配的
   - `limit` 本次最多发几个目录（防一次刷屏）
   - `archive` 默认勾选，发完把目录删掉（同一名字以后可重用）

## 一次性配置

1. [QQ 开放平台](https://q.qq.com) → 你的机器人 → 开发设置：拿 **AppID** / **AppSecret**
2. 把机器人添加到目标群
3. 拿到该群的 **group_openid**（不是群号）：机器人进群后 @ 它一句，事件推送里带 `group_openid`；或在你自己接收端日志里找
4. 仓库 Settings → Secrets and variables → Actions，建三个 secret：
   - `QQ_APP_ID`
   - `QQ_APP_SECRET`
   - `QQ_GROUP_OPENID`


## 首次配置：自动抓 group_openid

`group_openid` 只能在「群里 @ 机器人」的事件里拿到，所以配了一个 Cloudflare Worker 当抓取器：

0. Worker 先加一个 Secret `QQ_SECRET`（= 机器人 AppSecret），否则回调验签会 1102
1. 开放平台 → 开发设置 → 回调地址填：`https://qqbot-openid.zerolost1014.workers.dev/callback`，勾选事件 `GROUP_AT_MESSAGE_CREATE`
2. 等平台回调验证通过（Worker 用 QQ_SECRET 做 ed25519 签名，签名密钥来自 Worker Secret `QQ_SECRET`）
3. 开放平台 → 沙箱/测试群配置**机器人要用的 AppID**（同一个 AppID 的 openid 才通用）
4. 在群里 @ 机器人 一句话 → Worker 把 `group_openid` 写进本仓库 `state/group_openid.json`
5. 下次跑 workflow，若 Secret `QQ_GROUP_OPENID` 为空或与状态文件不同，会自动换成最新抓到的那个

Worker 源码在 `worker/index.js`，独立部署为 `qqbot-openid`，不影响其它 Worker。

## 限制（官方规则）

- 走 Markdown 消息（`msg_type=2`）+ **素材库**（`/v2/media-images/*`）：图片先上传平台拿 `qqbot-media://` 引用，再由平台转存，首图或过期后会自动重新转存；因此不依赖任何公网 URL
- 图片：png / jpg / gif / webp，单张 ≤10MB；素材库单机器人上限 100 张
- **自动清理**：每次发送前先查素材库，按最旧优先删除，给本次要发的图腾出位置（默认预留 20 张 `QQ_MEDIA_RESERVE`）。已发出去的消息不受影响
- 注意：素材库的素材是**全机器人共享**的，单账号 100 张上限；长期高频用建议偶尔清理
- 主动消息：单群 20 条/分钟、每群每天 1000 条；单条消息 5 张图，多条之间隔 4s，多目录之间隔 15s
- 文字消息不允许含 URL，脚本不发链接
- 私有仓库图片由 Actions 读取后以二进制上传，**不会**产生公开链接

## 本地自测

```bash
python3 tests/mock_md_test.py                  # 假服务端跑通 Markdown 图文流程
python3 tools/qqbot_md_send.py --job jobs/<目录> --dry-run
```
