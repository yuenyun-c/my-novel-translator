import sqlite3

def create_database():
    # สร้างและเชื่อมต่อฐานข้อมูล (ถ้ายังไม่มีไฟล์นี้ มันจะสร้างให้ใหม่ทันที)
    conn = sqlite3.connect('novel_database.db')
    c = conn.cursor()

    # 1. สร้างตาราง "novels" (เก็บรายชื่อเรื่อง)
    c.execute('''
        CREATE TABLE IF NOT EXISTS novels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            original_url TEXT
        )
    ''')

    # 2. สร้างตาราง "chapters" (เก็บเนื้อหาตอนต่างๆ)
    c.execute('''
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            novel_id INTEGER,
            chapter_number INTEGER,
            content TEXT,
            next_url TEXT,
            FOREIGN KEY(novel_id) REFERENCES novels(id)
        )
    ''')

    # 3. สร้างตาราง "glossary" (เก็บคลังคำศัพท์ของแต่ละเรื่อง)
    c.execute('''
        CREATE TABLE IF NOT EXISTS glossary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            novel_id INTEGER,
            chinese_word TEXT,
            thai_word TEXT,
            FOREIGN KEY(novel_id) REFERENCES novels(id)
        )
    ''')

    conn.commit()
    conn.close()
    print("🗄️ สร้างฐานข้อมูล 'novel_database.db' สำเร็จแล้ว! โกดังของเราพร้อมใช้งานครับ")

if __name__ == '__main__':
    create_database()