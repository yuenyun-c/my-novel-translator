import sqlite3

conn = sqlite3.connect('novel_database.db')
try:
    # เพิ่มคอลัมน์ title เข้าไปในตาราง chapters สำหรับเก็บชื่อตอน
    conn.execute('ALTER TABLE chapters ADD COLUMN title TEXT DEFAULT ""')
    conn.commit()
    print("✅ อัปเกรดฐานข้อมูลเพิ่มช่อง 'ชื่อตอน' เรียบร้อย!")
except Exception as e:
    print("💡 ช่องนี้อาจจะมีอยู่แล้วหรือฐานข้อมูลอัปเกรดแล้ว:", e)
conn.close()