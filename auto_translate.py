import os
import json
import re
import sys
from urllib.parse import urljoin

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from openai import OpenAI

# ==========================================
# ⚙️ 1. ตั้งค่าระบบ
# ==========================================
API_KEY = "sk-e0d99922eba74ae4bfe51720956ac3c6" 
client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

URL_TO_READ = "https://www.69shuba.com/txt/32121/22963802"

# ==========================================
# 🏷️ ฟังก์ชันให้ AI วิเคราะห์ เลขตอน และ ชื่อตอน อัตโนมัติ
# ==========================================
def extract_chapter_info(raw_text):
    print("🔍 กำลังให้ AI วิเคราะห์ค้นหาเลขตอนและชื่อตอนต้นฉบับ...")
    prompt = """จงอ่านเนื้อหานิยายที่ได้รับ แล้วสกัดหา 'เลขตอน (เฉพาะตัวเลข)' และ 'ชื่อตอน (แปลเป็นไทยแล้ว)' 
    ส่งผลลัพธ์กลับมาเป็นรูปแบบ JSON เท่านั้น ห้ามพิมพ์ข้อความอธิบายอื่นใดเด็ดขาด
    
    ตัวอย่างผลลัพธ์:
    {"number": 400, "title": "ฟาร์มสัตว์อสูรในวันสิ้นโลก"}
    
    หากในเนื้อหาไม่ระบุเลขตอน ให้ใช้เลข 1 และถ้าไม่ระบุชื่อตอน ให้ใช้คำว่า "ตอนที่ไม่มีชื่อ" """
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": raw_text[:600]} # ส่งเฉพาะ 600 ตัวแรกเพื่อประหยัดเวลา
            ]
        )
        result_text = response.choices[0].message.content
        
        import re
        import json
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            return int(data.get('number', 1)), data.get('title', 'ตอนที่ไม่มีชื่อ')
    except Exception as e:
        print("⚠️ สกัดชื่อตอนล้มเหลว:", e)
    return 1, "ตอนที่ไม่มีชื่อ"

# ==========================================
# 🕷️ 2. ฟังก์ชันกวาดเนื้อหา (และหาลิงก์ตอนต่อไป)
# ==========================================
def scrape_novel_chapter(url):
    print(f"🕷️ [1/4] กำลังวิ่งไปกวาดเนื้อหาจากเว็บ: {url}")
    user_data_dir = "./browser_data"
    
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(user_data_dir=user_data_dir, headless=False)
        page = browser.pages[0] if browser.pages else browser.new_page()
        try:
            page.goto(url, timeout=60000)
            page.wait_for_selector('div.txtnav', timeout=30000) 
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # 1. ดึงเนื้อหานิยาย
            content_div = soup.find('div', class_='txtnav')
            
            # 2. 🎯 ดึงลิงก์ "ตอนต่อไป" (下一章)
            next_url = None
            # ค้นหาปุ่มที่มีคำว่า 下一章 (ตอนต่อไป)
            next_button = soup.find('a', string=re.compile('下一章'))
            if next_button and 'href' in next_button.attrs:
                # บางทีเว็บให้ลิงก์มาแบบย่อ เราต้องใช้ urljoin เพื่อประกอบเป็นลิงก์เต็ม
                next_url = urljoin(url, next_button['href'])
                # ป้องกันกรณีที่มันเป็นหน้าสุดท้ายแล้วลิงก์วนกลับไปหน้าสารบัญ
                if "catalog" in next_url or next_url == url:
                    next_url = None
            
            if content_div:
                print(f"✅ ดึงเนื้อหาสำเร็จ! (ลิงก์ตอนต่อไปที่พบ: {next_url})")
                text = content_div.get_text(separator='\n', strip=True)
                # คืนค่ากลับไป 2 อย่าง: เนื้อหา และ ลิงก์ตอนถัดไป
                return text, next_url
                
            return None, None
            
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดตอนดึงเว็บ: {e}")
            return None, None
        finally:
            browser.close()

# ==========================================
# 🔍 3. ฟังก์ชันวิเคราะห์คลังคำศัพท์อัตโนมัติ (Auto-Glossary)
# ==========================================
def extract_glossary(raw_text):
    print("🔍 [2/4] กำลังให้ AI วิเคราะห์และสกัดคำศัพท์เฉพาะพร้อมจัดหมวดหมู่...")
    
    prompt = """คุณคือผู้เชี่ยวชาญด้านการวิเคราะห์เนื้อหานิยาย จงอ่านเนื้อหาที่ได้รับและสกัด 'คำศัพท์เฉพาะ' ออกมา 
    
    กฎเหล็กขั้นเด็ดขาด:
    1. ส่งผลลัพธ์กลับมาเป็นรูปแบบ JSON เท่านั้น ห้ามพิมพ์ข้อความอธิบายอื่นๆ
    2. รูปแบบ JSON ต้องเป็น Dictionary ที่ซ้อน Dictionary โดยระบุคำแปลไทย (th) และหมวดหมู่ (cat)
    3. หมวดหมู่ (cat) บังคับให้ใช้แค่ 3 คำนี้เท่านั้น: "character" (ตัวละคร), "title" (สถานที่/ตำแหน่ง/วิชา), "term" (คำศัพท์ทั่วไป)
    
    ตัวอย่างรูปแบบ JSON ที่ถูกต้องเป๊ะๆ:
    {
        "秦书剑": {"th": "ฉินชูเจี้ยน", "cat": "character"},
        "凉山寨": {"th": "ค่ายเหลียงซาน", "cat": "title"},
        "锻体经": {"th": "คัมภีร์หลอมกายา", "cat": "title"},
        "炮灰NPC": {"th": "NPCสมุนกี้", "cat": "term"}
    }"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": raw_text}
            ]
        )
        
        result_text = response.choices[0].message.content
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        
        if json_match:
            glossary_dict = json.loads(json_match.group(0))
            print("✅ สร้างคลังคำศัพท์สำเร็จ! รายการที่พบ:")
            for k, v in glossary_dict.items():
                # ดักจับกรณี AI ดื้อ ส่งมาเป็น String แบบเก่า
                th_word = v['th'] if isinstance(v, dict) else v
                cat_word = v['cat'] if isinstance(v, dict) else 'term'
                print(f"   - [{cat_word}] {k} -> {th_word}")
            return glossary_dict
        else:
            return {}
    except Exception as e:
        print(f"❌ วิเคราะห์คำศัพท์ล้มเหลว: {e}")
        return {}

# ==========================================
# 🧠 4. ฟังก์ชันแปลภาษาด้วย AI (หั่นท่อน + สแกนจีน + บังคับเว้นบรรทัด)
# ==========================================
def translate_to_thai(raw_text, glossary_dict):
    print("🧠 [3/4] กำลังเริ่มกระบวนการแปล (ใช้ระบบหั่นท่อน + สแกนภาษาจีน + จัดบรรทัด)...")
    
    # 1. เตรียมกฎ Glossary
    glossary_rules = ""
    if glossary_dict:
        rules = []
        for k, v in glossary_dict.items():
            # ดึงเฉพาะคำแปลไทยมาใช้ (รองรับข้อมูลที่ดึงมาแบบจัดหมวดหมู่แล้ว)
            th_word = v['th'] if isinstance(v, dict) else v
            rules.append(f"'{k}' ให้แปลว่า '{th_word}'")
        glossary_rules = "\n    7. คลังคำศัพท์บังคับ (Glossary) ห้ามแปลเป็นคำอื่นเด็ดขาด:\n       - " + "\n       - ".join(rules)

    # 🌟 เพิ่มกฎข้อ 6 บังคับเรื่องการเว้นบรรทัดขั้นเด็ดขาด
    system_prompt = f"""คุณเป็นสุดยอดนักแปลนิยายระดับปรมาจารย์ กฎเหล็กในการทำงานของคุณคือ:
    1. วิเคราะห์แนวเรื่องและปรับสำนวนให้เข้ากับบริบท
    2. บังคับแปลเป็น "ภาษาไทย 100%" เท่านั้น ห้ามทับศัพท์ภาษาต้นทาง
    3. รูปแบบข้อความธรรมดา ห้ามใช้เครื่องหมาย Markdown
    4. รักษาความหมายของต้นฉบับให้ครบถ้วน ห้ามแต่งเติม หรือตัดทอน
    5. เรียบเรียงโครงสร้างประโยคให้ลื่นไหล อ่านง่าย
    6. สำคัญสูงสุด: บังคับรักษา "การเว้นบรรทัด (Line Breaks)" และ "ย่อหน้า" ตามต้นฉบับเป๊ะๆ ห้ามนำข้อความมาต่อกันเป็นพรืดเด็ดขาด!{glossary_rules}"""

    # 2. ระบบหั่นท่อนข้อความ (Chunking)
    paragraphs = raw_text.split('\n')
    chunks = []
    current_chunk = ""
    max_length = 1500 

    for p in paragraphs:
        if len(current_chunk) + len(p) > max_length:
            chunks.append(current_chunk.strip())
            current_chunk = p + "\n"
        else:
            current_chunk += p + "\n"
    if current_chunk:
        chunks.append(current_chunk.strip())

    translated_full_text = ""
    total_chunks = len(chunks)

    # 3. ทยอยส่งแปลทีละก้อน 
    for i, chunk in enumerate(chunks):
        if not chunk: continue
        print(f"   ⏳ กำลังแปลส่วนที่ {i+1}/{total_chunks}...")
        
        # 🌟 ย้ำเตือนในคำสั่งรายก้อนอีกรอบเรื่องการเว้นบรรทัด
        user_prompt = f"จงแปลเนื้อหานิยายต่อไปนี้เป็น 'ภาษาไทยล้วน 100%' และ 'บังคับเว้นบรรทัดย่อหน้าตามต้นฉบับเป๊ะๆ':\n\n{chunk}"

        max_retries = 2 
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                translated_chunk = response.choices[0].message.content
                
                # ระบบสแกนหาอักษรจีน
                if re.search(r'[\u4e00-\u9fff]', translated_chunk):
                    print(f"      ⚠️ ตรวจพบภาษาจีนหลงเหลือ! กำลังสั่งแปลซ่อมแซม (รอบที่ {attempt + 1})...")
                    user_prompt = f"ผลลัพธ์ยังมีภาษาจีนปนอยู่! จงแปลใหม่ ห้ามมีอักษรจีน (Hanzi) แม้แต่ตัวเดียว และ 'ต้องเว้นบรรทัดตามต้นฉบับ':\n\n{chunk}"
                else:
                    # 🌟 ใช้ .strip() เพื่อตัดช่องว่างส่วนเกิน ก่อนจะเชื่อมด้วย \n\n ให้สวยงาม
                    translated_full_text += translated_chunk.strip() + "\n\n"
                    break 
                    
            except Exception as e:
                print(f"❌ เกิดข้อผิดพลาดตอนแปลส่วนที่ {i+1}: {e}")
                return None
            
            if attempt == max_retries - 1:
                print(f"      ⏭️ ข้ามการซ่อมแซมส่วนที่ {i+1} (อาจมีภาษาจีนหลงเหลือเล็กน้อย)")
                translated_full_text += translated_chunk.strip() + "\n\n"

    print("✅ แปลภาษาสำเร็จครบทุกส่วน!")
    return translated_full_text.strip()

# ==========================================
# 💾 5. ฟังก์ชันบันทึกเป็นไฟล์ข้อความ   
# ==========================================
def save_to_file(text, filename="translated_chapter.txt"):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"💾 [4/4] เซฟไฟล์สำเร็จ! นิยายถูกบันทึกไว้ที่: {filename}")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดตอนเซฟไฟล์: {e}")

# ==========================================
# 🚀 6. สั่งให้ระบบทำงานตามลำดับ (โหมดแปลต่อเนื่อง)
# ==========================================
if __name__ == "__main__":
    print("="*50)
    print("🚀 เริ่มระบบแปลนิยายอัตโนมัติ (โหมดแปลต่อเนื่อง) 🚀")
    print("="*50)
    
    current_url = URL_TO_READ
    max_chapters = 3  # 🛑 กำหนดจำนวนตอนที่ต้องการแปลรวดเดียว (ตั้งไว้ 3 ตอนก่อน ป้องกันรันเพลิน)
    
    for i in range(1, max_chapters + 1):
        print(f"\n📚 === กำลังดำเนินการตอนที่ {i}/{max_chapters} ===")
        
        # 1. ดึงข้อความ และ ลิงก์ตอนต่อไป
        chapter_text, next_chapter_url = scrape_novel_chapter(current_url)
        
        if chapter_text:
            # 2. สกัดคำศัพท์ และ แปลภาษา
            extracted_glossary = extract_glossary(chapter_text)
            translated_text = translate_to_thai(chapter_text, extracted_glossary)
            
            if translated_text:
                # 3. เซฟไฟล์โดยรันเลขตอนอัตโนมัติ
                file_name = f"chapter_{i}.txt"
                save_to_file(translated_text, file_name)
                
                # 4. เช็กว่ามีตอนต่อไปไหม เพื่อวนลูป
                if next_chapter_url:
                    print(f"⏭️ เตรียมตัวแปลตอนต่อไป: {next_chapter_url}")
                    current_url = next_chapter_url # อัปเดตลิงก์เป็นตอนใหม่
                else:
                    print("🛑 ดูเหมือนจะเป็นตอนล่าสุดแล้ว ไม่มีปุ่มตอนต่อไปครับ หยุดการทำงาน")
                    break
        else:
            print(f"❌ ดึงข้อมูลตอนที่ {i} ไม่สำเร็จ ขอหยุดการทำงานแค่นี้")
            break
            
    print("\n" + "="*50)
    print("🎉 เสร็จสิ้นภารกิจแปลต่อเนื่อง!")