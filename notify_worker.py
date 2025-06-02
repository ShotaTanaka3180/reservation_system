# notify_worker.py

import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from dotenv import load_dotenv
import requests

# 環境変数の読み込み（Renderでは load_dotenv はなくても OK だがローカル実行では必要）
load_dotenv()

DATABASE_URL = os.environ.get("postgresql://reservation_db_xhwh_user:54vyztYt01jG1ukUzJ2csLxRiCk20qzS@dpg-d0rsg9k9c44c73chs6p0-a.oregon-postgres.render.com:5432/reservation_db_xhwh")
DISCORD_WEBHOOK_URL_REMIND = os.environ.get("https://discord.com/api/webhooks/1376787046361862204/zxoxntBDR05dyzMfYcquk9NUY6JtXt0WO3PbyQ_9sCX5euINOALxSLcExUYYE558Jwk1")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def send_discord_notification(msg):
    try:
        r = requests.post(DISCORD_WEBHOOK_URL_REMIND,
                          json={"content": msg},
                          headers={"Content-Type": "application/json"})
        r.raise_for_status()
    except Exception as e:
        print("通知失敗:", e)

def check_and_notify():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM reservations WHERE notified = FALSE;")
    rows = cur.fetchall()
    now = datetime.now()
    for r in rows:
        dt = r["datetime"]
        if isinstance(dt, str):
            dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        delta = (dt - now).total_seconds()
        if 3300 <= delta <= 3900:  # 約55〜65分前
            msg = (
                f"【リマインド】この後会議ありますよ!\n"
                f"担当者: {r['applicant']}\n"
                f"部屋: {r['room']}\n"
                f"日時: {r['date']} {r['time_slot']}\n"
                f"会議名: {r['meeting_name']}"
            )
            send_discord_notification(msg)
            cur.execute("UPDATE reservations SET notified = TRUE WHERE id = %s;", (r["id"],))
            conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_and_notify()

