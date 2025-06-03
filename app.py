from dotenv import load_dotenv
import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import threading
import time
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "secret_key_for_flash"

# .envファイルから環境変数読み込み（UTF-8で保存した.envを用意してください）
load_dotenv()

# 環境変数からDATABASE_URLを取得し、strip()で余計な空白・改行を除去
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.strip()

print("DATABASE_URL (repr):", repr(DATABASE_URL))  # 環境変数の内容を不可視文字込みでチェック

if DATABASE_URL is None or DATABASE_URL == "":
    raise RuntimeError("DATABASE_URLが設定されていません。")

# Discord Webhook URLs（環境変数がなければデフォルト値）
DISCORD_WEBHOOK_URL_NOTIFY = os.environ.get(
    "DISCORD_WEBHOOK_URL_NOTIFY",
    "https://discord.com/api/webhooks/1377180247119757332/707LUp9xyNCEwLmNdV45ynylLJIldIJol7oMtIlMVPLb2GR7Lma_H1Nwsi0qgna6uMzb"
)
DISCORD_WEBHOOK_URL_REMIND = os.environ.get(
    "DISCORD_WEBHOOK_URL_REMIND",
    "https://discord.com/api/webhooks/1376787046361862204/zxoxntBDR05dyzMfYcquk9NUY6JtXt0WO3PbyQ_9sCX5euINOALxSLcExUYYE558Jwk1"
)

TIME_SLOT_TO_TIME = {
    "1限": (9, 0),
    "2限": (10, 40),
    "昼休み": (12, 20),
    "3限": (13, 0),
    "4限": (14, 40),
    "5限": (16, 20),
    "6限": (18, 0),
    "夜（22時）": (22, 00),
}

ROOM_COLOR = {
    "自治会室１": "#f8b400",
    "自治会室２": "#4caf50",
    "小ホール": "#2196f3",
    "208": "#f321ad",
    "308": "#9c27b0",
    "309": "#ff5722",
    "discord通話": "#5116db",
    "その他": "#5116db"
}

lock = threading.Lock()

def get_db_connection():
    # psycopg2.connectに文字列をそのまま渡す（dsnパラメータ名を明示）
    return psycopg2.connect(dsn=DATABASE_URL)

def load_reservations():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM reservations ORDER BY datetime;")
    reservations = cur.fetchall()
    cur.close()
    conn.close()
    return reservations

def save_reservation(applicant, room, date, time_slot, meeting_name, dt):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO reservations (applicant, room, date, time_slot, meeting_name, datetime, notified)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
    """, (applicant, room, date, time_slot, meeting_name, dt, False))
    conn.commit()
    cur.close()
    conn.close()

def delete_reservation_by_id(res_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM reservations WHERE id = %s;", (res_id,))
    conn.commit()
    cur.close()
    conn.close()

def send_discord_notification(webhook_url, msg):
    import requests
    try:
        r = requests.post(webhook_url,
                          json={"content": msg},
                          headers={"Content-Type": "application/json"})
        r.raise_for_status()
    except Exception as e:
        print("Discord通知エラー:", e)

def check_and_notify():
    while True:
        now = datetime.now()
        with lock:
            rs = load_reservations()
            for r in rs:
                if not r.get("notified", False):
                    dt = r["datetime"]
                    if isinstance(dt, str):
                        dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
                    if 0 < (dt - now).total_seconds() <= 3600:
                        remind = (
                            f"【リマインド】この後会議ありますよ!\n"
                            f"担当者: {r['applicant']}\n"
                            f"部屋: {r['room']}\n"
                            f"日時: {r['date']} {r['time_slot']}\n"
                            f"会議名: {r['meeting_name']}")
                        send_discord_notification(DISCORD_WEBHOOK_URL_REMIND, remind)
                        # 通知済みに更新
                        conn = get_db_connection()
                        cur = conn.cursor()
                        cur.execute("UPDATE reservations SET notified = TRUE WHERE id = %s;", (r["id"],))
                        conn.commit()
                        cur.close()
                        conn.close()
        time.sleep(60)

@app.route('/')
def index():
    rs = load_reservations()
    rooms = list(ROOM_COLOR.keys())
    time_slots = list(TIME_SLOT_TO_TIME.keys())
    return render_template('reserve.html', reservations=rs, rooms=rooms, time_slots=time_slots)

@app.route('/reserve', methods=['POST'])
def reserve():
    applicant = request.form['applicant']
    room = request.form['room']
    date = request.form['date']
    time_slot = request.form['time_slot']
    meeting_name = request.form['meeting_name']

    with lock:
        rs = load_reservations()
        for r in rs:
            if r["room"] == room and str(r["date"]) == date and r["time_slot"] == time_slot:
                flash("エラー：同じ部屋・時間帯は既に予約されています。", "error")
                return redirect(url_for('index'))

        h, m = TIME_SLOT_TO_TIME[time_slot]
        dt = datetime.strptime(date, "%Y-%m-%d").replace(hour=h, minute=m, second=0)
        save_reservation(applicant, room, date, time_slot, meeting_name, dt)

    msg = (
        f"【予約通知】\n"
        f"担当者: {applicant}\n"
        f"部屋: {room}\n"
        f"日時: {date} {time_slot}\n"
        f"会議名: {meeting_name}")
    send_discord_notification(DISCORD_WEBHOOK_URL_NOTIFY, msg)
    flash("予約が完了しました！", "success")
    return redirect(url_for('index'))

@app.route('/cancel/<int:reservation_id>', methods=['POST'])
def cancel(reservation_id):
    with lock:
        rs = load_reservations()
        if any(r["id"] == reservation_id for r in rs):
            res_to_delete = next(r for r in rs if r["id"] == reservation_id)
            delete_reservation_by_id(reservation_id)
            flash("予約をキャンセルしました。", "success")
            msg = (
                f"【予約キャンセル】\n"
                f"担当者: {res_to_delete['applicant']}\n"
                f"部屋: {res_to_delete['room']}\n"
                f"日時: {res_to_delete['date']} {res_to_delete['time_slot']}\n"
                f"会議名: {res_to_delete['meeting_name']}")
            send_discord_notification(DISCORD_WEBHOOK_URL_NOTIFY, msg)
        else:
            flash("キャンセル失敗：無効な予約です。", "error")
    return redirect(url_for('index'))

@app.route('/calendar')
def calendar_page():
    return render_template('calendar.html')

@app.route('/api/reservations')
def api_reservations():
    rs = load_reservations()
    events = []
    for r in rs:
        start = r["datetime"]
        if isinstance(start, str):
            start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
        else:
            start_dt = start
        end_dt = start_dt + timedelta(minutes=90)
        events.append({
            "title": f"{r['room']} – {r['meeting_name']}",
            "start": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "color": ROOM_COLOR.get(r["room"], "#888888")
        })
    return jsonify(events)

if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=check_and_notify, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
