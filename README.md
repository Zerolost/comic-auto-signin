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

实际发到群里的样子：

```
💬 20261126-晚点吃啥          ← 目录名（配文）
💬 1.猫咖                     ← 第一张图：文件名（去后缀）
🖼 1.猫咖.png
💬 2.新开的店
🖼 2.新开的店.jpeg
```

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

## 限制（官方规则）

- 图片：png / jpg / bmp。≤5MB 直传，更大自动走分片上传；单图 20MB 软上限
- 主动消息：单群 20 条/分钟、每群每天 1000 条；脚本每条间隔 1.2s，多目录之间隔 15s
- 文字消息不允许含 URL，脚本不发链接
- 私有仓库图片由 Actions 读取后以二进制上传，**不会**产生公开链接

## 本地自测

```bash
python3 tests/mock_bot_test.py                      # 假服务端跑完整流程
python3 tools/qqbot_group_send.py --job jobs/<目录> --dry-run
```
