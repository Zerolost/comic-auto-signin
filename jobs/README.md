# jobs/

每个子目录 = 一次推送：

```
jobs/20261126-示例/
├─ text.md        正文（markdown，可省）
├─ images.txt     图片顺序，一行一个文件名（可省，默认按文件名排序）
└─ images/        图片
```

上传完去 Actions → 「QQ 邮箱推送图片」→ Run workflow。
以 `.` 或 `_` 开头的目录不会被当成任务（存档放 `jobs/_sent/`）。
