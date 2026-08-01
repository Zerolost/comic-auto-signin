import logging
import os
import json
import requests
import time
from datetime import datetime, timedelta
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

# Telegram 推送函数
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

# 过滤关键词
KEYWORDS = ["🎉", "登录账号", "显示用户名", "金币余额", "===="]

def extract_summary(log_lines):
    """从完整日志中提取签到结果摘要"""
    filtered = [line for line in log_lines if any(k in line for k in KEYWORDS)]
    return "\n".join(filtered) if filtered else "（未提取到结果摘要，请检查日志）"

if __name__ == "__main__":
    # 记录开始时间
    start_time = time.time()
    beijing_time = datetime.utcnow() + timedelta(hours=8)
    start_time_str = beijing_time.strftime("%Y-%m-%d %H:%M:%S")

    logging.info("=" * 50)
    logging.info("🚀 ComicsPuncher 启动")
    logging.info("=" * 50)
    
    # 解析配置
    pica_accounts, jm_accounts, proxy = parse_accounts_config()
    
    # 挂载日志收集器
    list_handler = ListHandler()
    list_handler.setFormatter(logging.Formatter('%(message)s'))
    logging.getLogger().addHandler(list_handler)
    
    # 检查配置
    if not pica_accounts and not jm_accounts:
        logging.error("❌ 配置中没有任何账号信息！")
        logging.error("   请在 ACCOUNTS_CONFIG 中至少配置一个平台的账号")
        exit(1)
    
    # 用于存放每个账号的摘要结果
    all_results = []
    
    # 执行哔咔打卡
    if pica_accounts:
        logging.info(f"\n🎨 开始执行 Pica 签到 ({len(pica_accounts)} 个账号)")
        for idx, account in enumerate(pica_accounts, 1):
            logging.info(f"\n--- Pica 账号 {idx}/{len(pica_accounts)} ---")
            list_handler.clear()
            pica = PicaPuncher(account["user"], account["password"], proxy)
            try:
                pica.run()
            except Exception as e:
                logging.error(f"Pica 账号 {idx} 异常: {e}")
            logs = list_handler.get_messages()
            summary = extract_summary(logs)
            if summary:
                all_results.append(f"【Pica账号{idx}】\n{summary}")
            else:
                all_results.append(f"【Pica账号{idx}】\n签到执行，但未获取到结果摘要。")
    else:
        logging.info("\n⏭️  未配置 Pica 账号，跳过")

    # 执行 JM 打卡
    if jm_accounts:
        logging.info(f"\n📚 开始执行 JM 签到 ({len(jm_accounts)} 个账号)")
        for idx, account in enumerate(jm_accounts, 1):
            logging.info(f"\n--- JM 账号 {idx}/{len(jm_accounts)} ---")
            list_handler.clear()
            jm = JmPuncher(account["user"], account["password"], proxy)
            try:
                jm.run()
            except Exception as e:
                logging.error(f"JM 账号 {idx} 异常: {e}")
            logs = list_handler.get_messages()
            summary = extract_summary(logs)
            if summary:
                all_results.append(f"【JM账号{idx}】\n{summary}")
            else:
                all_results.append(f"【JM账号{idx}】\n签到执行，但未获取到结果摘要。")
    else:
        logging.info("\n⏭️  未配置 JM 账号，跳过")
    
    logging.info("\n" + "=" * 50)
    logging.info("✅ 所有任务执行完毕")
    logging.info("=" * 50)

    # 移除日志收集器
    logging.getLogger().removeHandler(list_handler)
    
    # 计算耗时
    elapsed = time.time() - start_time
    if elapsed < 60:
        duration_str = f"{elapsed:.1f}秒"
    else:
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        duration_str = f"{minutes}分{seconds}秒"

    # 组装推送消息
    header = f"签到任务完成！\n开始时间: {start_time_str}\n任务用时: {duration_str}\n"
    if all_results:
        body = "\n\n".join(all_results)
        final_msg = header + "\n" + body
    else:
        final_msg = header + "\n无任何签到结果输出。"

    send_tg_message(final_msg)