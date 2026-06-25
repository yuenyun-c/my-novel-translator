from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import os

url = "https://www.69shuba.com/txt/32121/22963802"

# สร้างโฟลเดอร์ชื่อ browser_data ไว้เก็บความจำ (คุกกี้/ประวัติ) ไว้ในโฟลเดอร์โปรเจกต์ของเรา
USER_DATA_DIR = "./browser_data" 

print(f"📌 กำลังเปิดเบราว์เซอร์ (แบบมีความจำ) ไปที่: {url}\n")

with sync_playwright() as p:
    # ใช้ launch_persistent_context แทน launch ธรรมดา เพื่อให้มันจำคุกกี้
    browser = p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR, 
        headless=False # เปิดหน้าจอไว้เหมือนเดิมเผื่อต้องกดครั้งแรก
    )
    
    # ดึงแท็บแรกที่เปิดขึ้นมาใช้
    page = browser.pages[0] if browser.pages else browser.new_page()
    
    try:
        # ให้เวลา 60 วินาที เผื่อรันครั้งแรกเราต้องใช้เวลาเอาเมาส์ไปคลิกยืนยันตัวตน
        page.goto(url, timeout=60000)
        
        # รอจนกว่ากล่องเนื้อหาจะโผล่
        page.wait_for_selector('div.txtnav', timeout=30000) 
        
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        content_div = soup.find('div', class_='txtnav')
        
        if content_div:
            extracted_text = content_div.get_text(separator='\n', strip=True)
            print("✨ --- เนื้อหาที่ดึงมาได้ --- ✨")
            print(extracted_text + "\n...\n\n[✅ ทะลวงระบบสำเร็จ!]")
        else:
            print("❌ ไม่พบเนื้อหา")
            
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")
        print("💡 ทริก: ถ้ารันครั้งแรกแล้วมันติดหน้ายืนยัน ให้เอาเมาส์ไปคลิกยืนยันตัวตนในหน้าต่าง Chrome ให้ผ่านก่อนนะ!")
        
    finally:
        browser.close()