from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
# 🌟 ดึงฟังก์ชันสกัดชื่อตอน (extract_chapter_info) เข้ามาใช้งาน
from auto_translate import scrape_novel_chapter, extract_glossary, translate_to_thai, extract_chapter_info

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect('novel_database.db')
    conn.row_factory = sqlite3.Row 
    return conn

@app.route('/')
def home():
    conn = get_db()
    novels = conn.execute('SELECT * FROM novels ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('index.html', novels=novels)

# ==========================================
# ➕ 1. เพิ่มนิยายเรื่องใหม่ (รองรับทั้ง ลิงก์ และ ตัวหนังสือดิบ)
# ==========================================
@app.route('/add_novel', methods=['POST'])
def add_novel():
    data = request.json
    title = data.get('title', 'นิยายเรื่องใหม่')
    url = data.get('url', '').strip()
    raw_text = data.get('raw_text', '').strip()
    
    if not url and not raw_text:
        return jsonify({"status": "error", "message": "กรุณากรอกลิงก์หรือวางเนื้อหาตัวหนังสือด้วยครับ"})

    conn = get_db()
    c = conn.cursor()
    # ถ้าไม่มี url ให้ใส่คำว่า "เพิ่มด้วยข้อความดิบ" แทน
    c.execute('INSERT INTO novels (title, original_url) VALUES (?, ?)', (title, url if url else "เพิ่มด้วยข้อความดิบ"))
    novel_id = c.lastrowid
    conn.commit()

    # แยกกรณี: ดึงจากลิงก์ หรือ ใช้ข้อความดิบ
    if url:
        chapter_text, next_url = scrape_novel_chapter(url)
    else:
        chapter_text, next_url = raw_text, ""

    if chapter_text:
        ch_number, ch_title = extract_chapter_info(chapter_text) # 🌟 สกัดเลขตอนและชื่อตอนจริง
        glossary = extract_glossary(chapter_text)
        translated_text = translate_to_thai(chapter_text, glossary)
        
        if translated_text:
            c.execute('''INSERT INTO chapters (novel_id, chapter_number, title, content, next_url) 
                         VALUES (?, ?, ?, ?, ?)''', (novel_id, ch_number, ch_title, translated_text, next_url))
            if glossary:
                for zh, data_dict in glossary.items():
                    th = data_dict['th'] if isinstance(data_dict, dict) else data_dict
                    cat = data_dict['cat'] if isinstance(data_dict, dict) else 'term'
                    c.execute('INSERT INTO glossary (novel_id, chinese_word, thai_word, category) VALUES (?, ?, ?, ?)', 
                              (novel_id, zh, th, cat))
            conn.commit()
            conn.close()
            return jsonify({"status": "success"})
            
    conn.close()
    return jsonify({"status": "error", "message": "เกิดข้อผิดพลาดในการประมวลผล หรือดึงเนื้อหาไม่สำเร็จ"})

# ==========================================
# 📖 2. หน้ารายละเอียดนิยาย (สารบัญ)
# ==========================================
@app.route('/novel/<int:novel_id>')
def novel_detail(novel_id):
    conn = get_db()
    novel = conn.execute('SELECT * FROM novels WHERE id = ?', (novel_id,)).fetchone()
    chapters = conn.execute('SELECT * FROM chapters WHERE novel_id = ? ORDER BY chapter_number ASC', (novel_id,)).fetchall()
    conn.close()
    return render_template('detail.html', novel=novel, chapters=chapters)

# ==========================================
# 📄 3. หน้าอ่านนิยาย (อัปเกรดส่ง ID ตอนก่อนหน้า/ถัดไป)
# ==========================================
@app.route('/read/<int:chapter_id>')
def read_chapter(chapter_id):
    conn = get_db()
    chapter = conn.execute('SELECT * FROM chapters WHERE id = ?', (chapter_id,)).fetchone()
    novel = conn.execute('SELECT * FROM novels WHERE id = ?', (chapter['novel_id'],)).fetchone()

    # 🔎 ค้นหา ID ของตอนก่อนหน้า (ตอนที่เลขน้อยกว่าตอนนี้ที่ใกล้ที่สุด)
    prev_chap = conn.execute('SELECT id FROM chapters WHERE novel_id = ? AND chapter_number < ? ORDER BY chapter_number DESC LIMIT 1',
                             (chapter['novel_id'], chapter['chapter_number'])).fetchone()
                             
    # 🔎 ค้นหา ID ของตอนถัดไป (ตอนที่เลขมากกว่าตอนนี้ที่ใกล้ที่สุด)
    next_chap = conn.execute('SELECT id FROM chapters WHERE novel_id = ? AND chapter_number > ? ORDER BY chapter_number ASC LIMIT 1',
                             (chapter['novel_id'], chapter['chapter_number'])).fetchone()

    conn.close()
    return render_template('read.html', novel=novel, chapter=chapter,
                           prev_id=prev_chap['id'] if prev_chap else None,
                           next_id=next_chap['id'] if next_chap else None)

# ==========================================
# ⏭️ 4. แปลตอนต่อไป (ดึงเลขตอนและชื่อตอนออโต้)
# ==========================================
@app.route('/translate_next/<int:novel_id>', methods=['POST'])
def translate_next(novel_id):
    conn = get_db()
    c = conn.cursor()
    last_chapter = c.execute('SELECT * FROM chapters WHERE novel_id = ? ORDER BY chapter_number DESC LIMIT 1', (novel_id,)).fetchone()
    
    if not last_chapter or not last_chapter['next_url']:
        conn.close()
        return jsonify({"status": "error", "message": "ไม่พบลิงก์ตอนต่อไป หรือเป็นตอนที่เพิ่มแบบข้อความดิบ"})
        
    next_url = last_chapter['next_url']
    glossary_rows = c.execute('SELECT chinese_word, thai_word FROM glossary WHERE novel_id = ?', (novel_id,)).fetchall()
    existing_glossary = {row['chinese_word']: row['thai_word'] for row in glossary_rows}
    
    chapter_text, new_next_url = scrape_novel_chapter(next_url)
    
    if chapter_text:
        ch_number, ch_title = extract_chapter_info(chapter_text) # 🌟 ดึงเลขตอนและชื่อตอนจริง
        new_extracted_glossary = extract_glossary(chapter_text)
        
        if new_extracted_glossary:
            for zh, data_dict in new_extracted_glossary.items():
                if zh not in existing_glossary:
                    th = data_dict['th'] if isinstance(data_dict, dict) else data_dict
                    cat = data_dict['cat'] if isinstance(data_dict, dict) else 'term'
                    c.execute('INSERT INTO glossary (novel_id, chinese_word, thai_word, category) VALUES (?, ?, ?, ?)', 
                              (novel_id, zh, th, cat))
                    existing_glossary[zh] = th 

        translated_text = translate_to_thai(chapter_text, existing_glossary)
        
        if translated_text:
            c.execute('''INSERT INTO chapters (novel_id, chapter_number, title, content, next_url) 
                         VALUES (?, ?, ?, ?, ?)''', (novel_id, ch_number, ch_title, translated_text, new_next_url))
            conn.commit()
            conn.close()
            return jsonify({"status": "success"})
            
    conn.close()
    return jsonify({"status": "error", "message": "เกิดข้อผิดพลาดในการแปลตอนต่อไป"})

# ==========================================
# 🔗 5. ระบบใส่ลิงก์ข้ามตอน (Jump Chapter)
# ==========================================
@app.route('/jump_chapter/<int:novel_id>', methods=['POST'])
def jump_chapter(novel_id):
    data = request.json
    url = data.get('url', '').strip()
    if not url: return jsonify({"status": "error", "message": "กรุณาใส่ลิงก์"})

    conn = get_db()
    c = conn.cursor()
    chapter_text, new_next_url = scrape_novel_chapter(url)
    
    if chapter_text:
        ch_number, ch_title = extract_chapter_info(chapter_text)
        glossary_rows = c.execute('SELECT chinese_word, thai_word FROM glossary WHERE novel_id = ?', (novel_id,)).fetchall()
        existing_glossary = {row['chinese_word']: row['thai_word'] for row in glossary_rows}
        
        new_extracted_glossary = extract_glossary(chapter_text)
        if new_extracted_glossary:
            for zh, data_dict in new_extracted_glossary.items():
                if zh not in existing_glossary:
                    th = data_dict['th'] if isinstance(data_dict, dict) else data_dict
                    cat = data_dict['cat'] if isinstance(data_dict, dict) else 'term'
                    c.execute('INSERT INTO glossary (novel_id, chinese_word, thai_word, category) VALUES (?, ?, ?, ?)', 
                              (novel_id, zh, th, cat))
                    existing_glossary[zh] = th 

        translated_text = translate_to_thai(chapter_text, existing_glossary)
        
        if translated_text:
            c.execute('''INSERT INTO chapters (novel_id, chapter_number, title, content, next_url) 
                         VALUES (?, ?, ?, ?, ?)''', (novel_id, ch_number, ch_title, translated_text, new_next_url))
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "message": f"ข้ามไปตอนที่ {ch_number} สำเร็จ!"})
            
    conn.close()
    return jsonify({"status": "error", "message": "ไม่สามารถดึงข้อมูลเพื่อข้ามตอนได้"})

# ==========================================
# ✏️ 6. ระบบแก้ไขชื่อเรื่องนิยาย
# ==========================================
@app.route('/edit_novel_title/<int:novel_id>', methods=['POST'])
def edit_novel_title(novel_id):
    data = request.json
    new_title = data.get('title', '').strip()
    if new_title:
        conn = get_db()
        conn.execute('UPDATE novels SET title = ? WHERE id = ?', (new_title, novel_id))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "ชื่อเรื่องห้ามเว้นว่าง"})

# ==========================================
# (ระบบคำศัพท์เดิม)
# ==========================================
@app.route('/edit_word/<int:word_id>', methods=['POST'])
def edit_word(word_id):
    data = request.json
    conn = get_db()
    conn.execute('UPDATE glossary SET chinese_word = ?, thai_word = ?, category = ? WHERE id = ?', 
                 (data.get('chinese_word'), data.get('thai_word'), data.get('category'), word_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/add_word/<int:novel_id>', methods=['POST'])
def add_word(novel_id):
    data = request.json
    conn = get_db()
    conn.execute('INSERT INTO glossary (novel_id, chinese_word, thai_word, category) VALUES (?, ?, ?, ?)', 
                 (novel_id, data.get('chinese_word'), data.get('thai_word'), data.get('category', 'term')))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/delete_word/<int:word_id>', methods=['POST'])
def delete_word(word_id):
    conn = get_db()
    conn.execute('DELETE FROM glossary WHERE id = ?', (word_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/glossary/<int:novel_id>')
def glossary_page(novel_id):
    conn = get_db()
    novel = conn.execute('SELECT * FROM novels WHERE id = ?', (novel_id,)).fetchone()
    words = conn.execute('SELECT * FROM glossary WHERE novel_id = ? ORDER BY id DESC', (novel_id,)).fetchall()
    conn.close()
    return render_template('glossary.html', novel=novel, words=words)

# ==========================================
# (ระบบแปลซ้ำ และ ลบนิยาย)
# ==========================================
@app.route('/retranslate/<int:chapter_id>', methods=['POST'])
def retranslate_chapter(chapter_id):
    conn = get_db()
    c = conn.cursor()
    chapter = c.execute('SELECT * FROM chapters WHERE id = ?', (chapter_id,)).fetchone()
    novel_id = chapter['novel_id']
    chapter_num = chapter['chapter_number']
    
    if chapter_num == 1:
        novel = c.execute('SELECT original_url FROM novels WHERE id = ?', (novel_id,)).fetchone()
        chapter_url = novel['original_url']
    else:
        # หาตอนก่อนหน้าแบบอิงตามตัวเลขตอนจริง
        prev_chapter = c.execute('SELECT next_url FROM chapters WHERE novel_id = ? AND chapter_number < ? ORDER BY chapter_number DESC LIMIT 1', (novel_id, chapter_num)).fetchone()
        chapter_url = prev_chapter['next_url'] if prev_chapter else None
        
    if not chapter_url or chapter_url == "เพิ่มด้วยข้อความดิบ": 
        return jsonify({"status": "error", "message": "ไม่พบลิงก์ต้นฉบับสำหรับการแปลซ้ำ"})
        
    chapter_text, _ = scrape_novel_chapter(chapter_url)
    if chapter_text:
        glossary_rows = c.execute('SELECT chinese_word, thai_word FROM glossary WHERE novel_id = ?', (novel_id,)).fetchall()
        translated_text = translate_to_thai(chapter_text, {r['chinese_word']: r['thai_word'] for r in glossary_rows})
        if translated_text:
            c.execute('UPDATE chapters SET content = ? WHERE id = ?', (translated_text, chapter_id))
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "message": "แปลใหม่สำเร็จ!"})
    conn.close()
    return jsonify({"status": "error", "message": "การแปลซ้ำล้มเหลว"})

@app.route('/delete_novel/<int:novel_id>', methods=['POST'])
def delete_novel(novel_id):
    conn = get_db()
    conn.execute('DELETE FROM glossary WHERE novel_id = ?', (novel_id,))
    conn.execute('DELETE FROM chapters WHERE novel_id = ?', (novel_id,))
    conn.execute('DELETE FROM novels WHERE id = ?', (novel_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

# ==========================================
# ✏️ 7. ระบบแก้ไขชื่อตอน
# ==========================================
@app.route('/edit_chapter_title/<int:chapter_id>', methods=['POST'])
def edit_chapter_title(chapter_id):
    data = request.json
    new_title = data.get('title', '').strip()
    if new_title:
        conn = get_db()
        conn.execute('UPDATE chapters SET title = ? WHERE id = ?', (new_title, chapter_id))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "ชื่อตอนห้ามเว้นว่าง"})

# ==========================================
# 🗑️ 8. ระบบลบตอนย่อย
# ==========================================
@app.route('/delete_chapter/<int:chapter_id>', methods=['POST'])
def delete_chapter(chapter_id):
    conn = get_db()
    conn.execute('DELETE FROM chapters WHERE id = ?', (chapter_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

# ==========================================
# 📝 9. ระบบแก้ไขเนื้อหานิยายด้วยตนเอง (Manual Edit Content)
# ==========================================
@app.route('/edit_chapter_content/<int:chapter_id>', methods=['POST'])
def edit_chapter_content(chapter_id):
    data = request.json
    new_content = data.get('content', '').strip()
    
    if new_content:
        conn = get_db()
        conn.execute('UPDATE chapters SET content = ? WHERE id = ?', (new_content, chapter_id))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "เนื้อหาห้ามเว้นว่าง"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)