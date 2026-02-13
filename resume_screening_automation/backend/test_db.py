from sqlalchemy import text
from db.session import engine

with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
    print("Neon DB connection OK")
