import logging
import os
import json
import requests
from pica_punch import PicaPuncher
from jm_punch import JmPuncher

# 日志格式设置
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def parse_accounts_config():
    """
    解析 JSON 格式的账号配置
    """
    accounts_json = os.getenv("ACCOUNTS_CONFIG")
    
    if not accounts_json:
        logging.error("❌ 未找到 ACCOUNTS_CONFIG 环境变量")
        logging.error("   请在 GitHub Secrets 中配置 ACCOUNTS_CONFIG")
        exit(1)
    
    try:
        config = json.loads(accounts_json)
        pica_accounts = config.get("pica", [])
        jm_accounts = config.get("jm", [])
        proxy = config.get("proxy", "")
        
        logging.info(f"📋 加载配置: {len(pica_accounts)} 个 Pica 账号, {len(jm_accounts)} 个 JM 账号")
        return pica_accounts, jm_accounts, proxy
    except json.JSONDecodeError as e:
        logging.error(f"❌ JSON 配置解析失败: {e}")
        exit(1)

# Telegram推送
class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []
    def emit(self, record):
        self.records.append(self.format(record))
    def get_messages(self):
        return self.records
    def clear(self):
        self.records.clear()

def send_tg_message(content: str):
    token = os.environ.get("TG_BOT_TOKEN")
    user_id = os.environ.get("TG_USER_ID")
    if not token or not user_id:
        logging.warning("未配置 TG_BOT_TOKEN 或 TG_USER_ID，跳过推送")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": user_id, "text": content}, timeout=10)
        if resp.status_code == 200:
            logging.info("✅ Telegram 推送成功")
        else:
            logging.error(f"❌ Telegram 推送失败：{resp.text}")
    except Exception as e:
        logging.error(f"❌ 推送异常：{e}")

if __name__ == "__main__":
    logging.info("=" * 50)
    logging.info("🚀 ComicsPuncher 启动")
    logging.info("=" * 50)
    
    # 解析配置
    pica_accounts, jm_accounts, proxy = parse_accounts_config()
    
    # 挂载日志收集器
    list_handler = ListHandler()
    list_handler.setFormatter(logging.Formatter('%(message)s'))  # 只保留消息文本，不带时间戳
    logging.getLogger().addHandler(list_handler)
    
    # 检查配置
    if not pica_accounts and not jm_accounts:
        logging.error("❌ 配置中没有任何账号信息！")
        logging.error("   请在 ACCOUNTS_CONFIG 中至少配置一个平台的账号")
        exit(1)
    
    # 执行哔咔打卡
    if pica_accounts:
        logging.info(f"\n🎨 开始执行 Pica 签到 ({len(pica_accounts)} 个账号)")
        for idx, account in enumerate(pica_accounts, 1):
            logging.info(f"\n--- Pica 账号 {idx}/{len(pica_accounts)} ---")
            pica = PicaPuncher(account["user"], account["password"], proxy)
            pica.run()
    else:
        logging.info("\n⏭️  未配置 Pica 账号，跳过")

    # 执行 JM 打卡
    if jm_accounts:
        logging.info(f"\n📚 开始执行 JM 签到 ({len(jm_accounts)} 个账号)")
        for idx, account in enumerate(jm_accounts, 1):
            logging.info(f"\n--- JM 账号 {idx}/{len(jm_accounts)} ---")
            jm = JmPuncher(account["user"], account["password"], proxy)
            jm.run()
    else:
        logging.info("\n⏭️  未配置 JM 账号，跳过")
    
    logging.info("\n" + "=" * 50)
    logging.info("✅ 所有任务执行完毕")
    logging.info("=" * 50)

    # 取出日志并推送
    logging.getLogger().removeHandler(list_handler)          # 先移除，避免后续推送日志被收集
    all_logs = list_handler.get_messages()                   # 获取所有捕获的日志
    if all_logs:
        final_msg = "\n".join(all_logs)                      # 用换行合并
    else:
        final_msg = "签到完成，但未产生任何日志。"
    send_tg_message(final_msg)