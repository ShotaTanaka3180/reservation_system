import psycopg2

DATABASE_URL = "postgresql://gicho:Kei821h5kei@localhost:5432/reservation_db"

try:
    conn = psycopg2.connect(DATABASE_URL)
    print("✅ データベース接続成功！")
    conn.close()
except Exception as e:
    print("❌ 接続失敗:", e)
