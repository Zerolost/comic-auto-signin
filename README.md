# QQ 邮箱发图

在 GitHub 上**点按钮**把仓库里的图片（可带文字）发到 QQ 邮箱 → 手机 QQ 的「QQ邮箱」提醒里直接看图。不需要服务器、不需要跑 QQ 协议端。

## 用法（每次发东西）

```
jobs/
└─ 20261126-晚点吃啥/        ← 目录名随便起，会当默认邮件标题
   ├─ text.md                ← 正文（markdown，可省）
   ├─ images.txt             ← 图片顺序（可省，默认按文件名拼音排序）
   └─ images/                ← 放图片，jpg/png/gif/webp/bmp
      ├─ 1.png
      └─ 2.jpg
```

1. 在 GitHub 网页把图和 text.md 上传到 `jobs/<目录名>/`
2. 仓库 **Actions → QQ 邮箱推送图片 → Run workflow**
   - `job`：留空 = 发 `jobs/` 下所有待发目录；填 `20261126` 这种前缀就只发匹配的
   - `subject`：邮件标题，留空用目录名
   - `archive`：默认勾选，发完把目录从 `jobs/` 删掉（同一目录名以后还能重用）
3. 收邮件：文字在正文，图片内嵌显示，QQ 手机端长按可保存

一次没发完？`job` 留空再点一次即可（已归档的不会重发）。

## 一次性配置（5 分钟）

1. **QQ 邮箱开 SMTP**：网页版邮箱 → 设置 → 账号 → 开启「POP3/SMTP 服务」→ 生成**授权码**（16 位，不是 QQ 密码）。可能要求先绑定手机/安全验证。
2. **仓库 Secrets**（Settings → Secrets and variables → Actions → New repository secret）：
   - `QQMAIL_USER` = 你的 QQ 邮箱，如 `123456@qq.com`
   - `QQMAIL_AUTH_CODE` = 上一步的授权码
   - `QQMAIL_TO` = 收件邮箱，发给自己就填同一个
3. 可选 Variables：`QQMAIL_MAX_IMAGES`（单封最多几张图，默认 20；体积上限约 23MB，超了会自动跳过剩下的）

> 想发到别的 QQ 邮箱也行：`QQMAIL_TO` 填对方地址即可，发件人仍是你的 QQ 邮箱。

## 注意

- 这是「邮件进 QQ 邮箱」路线：手机装 QQ 并开启 QQ邮箱 提醒，通知栏就能点开看图；不是往 QQ 聊天窗口里发消息（那需要挂着 QQ 协议端）。
- 公开仓库里图片是公开的；不想公开就把整个仓库设成 private（Actions 照常可用，只是私有仓库每月有免费额度）。
- 图片按文件名排序，想控顺序就写 `images.txt`，一行一个文件名。

## 本地测试

```bash
cd /var/minis/workspace/qq-mail
python3 tools/qqmail.py --job jobs/<目录名> --dry-run
```
