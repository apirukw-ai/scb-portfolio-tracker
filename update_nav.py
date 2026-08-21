import re
import json
import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

def fetch_from_scbam_official(fund_code):
    """ ดึงราคา NAV ตรงจากหน้าตารางราคากองทุน SCBAM (scbam.com/th/fund/nav) """
    clean_code = fund_code.strip()
    # แปลงชื่อรูปแบบต่างๆ เช่น SCBWORLD(E) หรือ SCBWORLD-E
    base_code = clean_code.replace('(E)', '').replace('-E', '').strip()
    
    url = "https://www.scbam.com/th/fund/nav"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            html = res.text
            # ค้นหารูปแบบชื่อกองทุนตามด้วยราคา NAV ทศนิยม 4 ตำแหน่ง
            patterns = [
                rf"{re.escape(clean_code)}.*?(\d+\.\d{{4}})",
                rf"{re.escape(base_code)}.*?\(E\).*?(\d+\.\d{{4}})",
                rf"{re.escape(base_code)}.*?-E.*?(\d+\.\d{{4}})"
            ]
            for pattern in patterns:
                match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
                if match:
                    return float(match.group(1))
    except Exception as e:
        print(f"  ⚠️ ดึงจาก SCBAM NAV Table ไม่สำเร็จ: {e}")
        
    return None

def fetch_from_finnomena(fund_code):
    """ ดึงราคา NAV จาก Finnomena API (สำรอง) """
    clean = fund_code.strip()
    variations = [clean, clean.replace('(E)', '-E'), clean.replace('-E', '(E)')]
    
    for symbol in variations:
        try:
            url = f"https://api.finnomena.com/fund/public/v1/fund/nav/latest?fund_symbol={symbol}"
            res = requests.get(url, headers=HEADERS, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if 'data' in data and data['data']:
                    nav = data['data'].get('nav') or data['data'].get('value')
                    if nav:
                        return float(nav)
        except Exception:
            pass
    return None

def main():
    print("🚀 เริ่มต้นระบบดึงข้อมูล NAV อัตโนมัติ (SCBAM + Finnomena)...")

    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        print("📖 อ่านไฟล์ index.html เรียบร้อย")
    except Exception as e:
        print(f"❌ อ่านไฟล์ index.html ไม่สำเร็จ: {e}")
        return

    # ค้นหารหัสกองทุนทั้งหมดใน index.html
    fund_codes = re.findall(r"code\s*:\s*['\"]([^'\"]+)['\"]", content)
    fund_codes = list(dict.fromkeys(fund_codes))

    if not fund_codes:
        print("❌ ไม่พบรหัสกองทุนในไฟล์ index.html")
        return

    print(f"📊 พบรายการกองทุนทั้งหมด {len(fund_codes)} รายการ: {', '.join(fund_codes)}")

    updated_count = 0
    new_content = content

    for code in fund_codes:
        print(f"🔍 กำลังดึง NAV ของ: {code} ...")
        
        # 1. ดึงจาก SCBAM Official NAV Table
        nav = fetch_from_scbam_official(code)
        
        # 2. ถ้าไม่พบ ให้ดึงจาก Finnomena เป็น Backup
        if nav is None:
            nav = fetch_from_finnomena(code)

        if nav is not None:
            print(f"  ✅ {code}: NAV ปัจจุบัน = {nav}")
            
            # อัปเดตค่า currentNav ใน index.html
            pattern = re.compile(
                r"(code\s*:\s*['\"]" + re.escape(code) + r"['\"].*?currentNav\s*:\s*)([0-9.]+)",
                re.DOTALL
            )
            if pattern.search(new_content):
                new_content = pattern.sub(r"\g<1>" + str(nav), new_content)
                updated_count += 1
            else:
                pattern_alt = re.compile(
                    r"(currentNav\s*:\s*)([0-9.]+)(.*?code\s*:\s*['\"]" + re.escape(code) + r"['\"])"
                )
                if pattern_alt.search(new_content):
                    new_content = pattern_alt.sub(r"\g<1>" + str(nav) + r"\g<3>", new_content)
                    updated_count += 1
        else:
            print(f"  ❌ {code}: ไม่พบข้อมูล NAV จากทุกช่องทาง")

    if updated_count > 0 and new_content != content:
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"🎉 บันทึกข้อมูล NAV ใหม่ลง index.html เรียบร้อย ({updated_count} กองทุน)")
    else:
        print("⚠️ ไม่มีข้อมูล NAV ที่อัปเดตเพิ่ม")

if __name__ == '__main__':
    main()
