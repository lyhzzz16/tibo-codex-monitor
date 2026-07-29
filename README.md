# Tibo Codex 动态监测

这是一个零费用的 GitHub Actions 版本：每 15 分钟读取公开的 Tibo 账号镜像页面，筛选 Codex/ChatGPT 使用限制、额度重置和恢复相关内容，并通过企业微信群机器人 Webhook 推送。

## 部署

1. 在 GitHub 新建一个公开仓库，例如 `tibo-codex-monitor`。
2. 上传本项目全部文件。
3. 在仓库的 `Settings → Secrets and variables → Actions` 新建 Secret：
   - 名称：`WECOM_WEBHOOK_URL`
   - 值：企业微信群机器人的 Webhook 地址
4. 在 `Actions` 中手动运行一次 `Monitor Tibo Codex updates`。
5. 首次运行只建立历史基线，不会把旧动态推送给你；之后出现匹配动态才推送。

## 说明

- 监测目标：`@thsottiaux`。
- 当前零费用版本使用公开的第三方页面镜像，不需要 X/Grok 账号；镜像可能延迟、改版或暂时不可用。
- GitHub Actions 的定时任务可能有平台延迟，15 分钟是近似频率，不是实时保证。
- Webhook 只放在 GitHub Secret 中，不写入代码或提交记录。
- 如果未来需要更稳定的 X 数据源，可把 `src/monitor.py` 的来源替换为获得授权的 RSS/API。
