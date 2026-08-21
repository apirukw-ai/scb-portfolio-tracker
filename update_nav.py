import re
import json
import requests
from bs4 import BeautifulSoup

# ตั้งค่า Header ป้องกันเว็บกองทุนบล็อก GitHub Action
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def fetch_nav_mfc(fund_code):
    """ ดึงราคา NAV ล่าสุดของกองทุน MFC """
    try:
        # ดึงจากหน้าค้นหากองทุน MFC
        url = f"https://www.mfcfund.com/Web/FundSearch/FundSearchDetail?fund_code={fund_code}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # ค้นหาตัวเลข NAV (ทศนิยม 4 ตำแหน่ง)
            text = soup.get_text()
            matches = re.findall(r'\b\d+\.\d{4}\b', text)
            if matches:
                return float(matches[0])
    except Exception as e:
        print(f"  ⚠️ ดึง {fund_code} จาก MFC ไม่สำเร็จ: {e}")
    return None

def main():
    print("🚀 เริ่มต้นระบบดึงข้อมูล NAV อัตโนมัติ...")

    # 1. อ่านไฟล์ index.html
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        print("📖 อ่านไฟล์ index.html เรียบร้อย")
    except Exception as e:
        print(f"❌ อ่านไฟล์ index.html ไม่สำเร็จ: {e}")
        return

    # 2. ค้นหาบล็อกข้อมูล funds ในไฟล์
    pattern = r'let funds = (\[.*?\]);'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        pattern = r'const funds = (\[.*?\]);'
        match = re.search(pattern, content, re.DOTALL)

    if not match:
        print("❌ ไม่พบตัวแปร funds ในไฟล์ index.html (กรุณาเช็กชื่อตัวแปร)")
        return

    funds_json_str = match.group(1)
    
    # 3. แปลงเป็น Python List/Dict
    try:
        # ปรับปรุงรูปแบบ JS Object ให้เป็น JSON ที่ถูกต้องก่อน parse
        clean_json = re.sub(r'(\w+):', r'"\1":', funds_json_str)
        clean_json = re.sub(r"'([^']*)'", r'"\1"', clean_json)
        funds_list = json.loads(clean_json)
        print(f"📊 พบรายการกองทุนทั้งหมด {len(funds_list)} รายการ")
    except Exception as e:
        print(f"⚠️ ไม่สามารถแปลงข้อมูล funds เป็น JSON ได้ สคริปต์จะใช้วิธีค้นหาและแทนที่ด้วย Regex")
        funds_list = []

    updated_count = 0

    # 4. วนลูปดึง NAV และอัปเดตข้อมูล
    if funds_list:
        for f in funds_list:
            code = f.get('code')
            if not code:
                continue
            
            nav = fetch_nav_mfc(code)
            if nav:
                print(f"  ✅ {code}: NAV ปัจจุบัน = {nav}")
                # เก็บค่า prevNav เดิมไว้ แล้วอัปเดต currentNav ใหม่
                if f.get('currentNav') and f['currentNav'] != nav:
                    f['prevNav'] = f['currentNav']
                f['currentNav'] = nav
                updated_count += 1
            else:
                print(f"  ❌ {code}: ไม่พบข้อมูล NAV")

        if updated_count > 0:
            new_funds_str = f"let funds = {json.dumps(funds_list, ensure_ascii=False, indent=4)};"
            content = re.sub(r'(let|const)\s+funds\s*=\s*\[.*?\];', new_funds_str, content, flags=re.DOTALL)
            
            with open('index.html', 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"🎉 บันทึกข้อมูล NAV ใหม่ลง index.html เรียบร้อย ({updated_count} กองทุน)")
        else:
            print("⚠️ ไม่มีข้อมูล NAV ที่อัปเดตเพิ่ม")
    else:
        print("⚠️ ข้ามกระบวนการอัปเดต เนื่องจากไม่สามารถดึงข้อมูลพอร์ตได้")

if __name__ == '__main__':
    main()
