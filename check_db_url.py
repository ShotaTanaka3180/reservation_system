from dotenv import load_dotenv
import os

# .env 読み込み
load_dotenv()

db_url = os.environ.get("DATABASE_URL")

print("DATABASE_URL raw (repr):", repr(db_url))
print("Type:", type(db_url))

try:
    encoded = db_url.encode("utf-8")
    print("UTF-8エンコード成功:", encoded)
except Exception as e:
    print("UTF-8エンコードでエラー:", e)
