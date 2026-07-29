# 执行计划

1. 使用公开页面镜像读取 `@thsottiaux` 的近期动态。
2. 用关键词筛选 Codex/ChatGPT 使用限制、额度重置、恢复或暂停相关表述。
3. 用 GitHub Actions 每 15 分钟执行一次。
4. 用 `state/seen.json` 去重，首次运行只建立基线。
5. 命中后通过企业微信群机器人 Webhook 发送 Markdown 消息。

待完成：创建 GitHub 仓库、上传文件、配置 `WECOM_WEBHOOK_URL`，并手动运行首次基线任务。
