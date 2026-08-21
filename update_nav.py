import re
import requests
import urllib.parse
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7'
}

def get_code_variations(code):
    clean = code.strip()
    variations = [clean]
    no_bracket = clean.replace('(', '').replace(')', '')
    variations.append(no_bracket)
    variations.append(clean.replace('(E)', '-E'))
    
    base_vars = list(variations)
    for v in base_vars:
        variations.append(v.replace('&', '%26'))
        variations.append(v.replace('&', ''))
        variations.append(v.replace('&', '-'))
        
    return list(dict.fromkeys(variations))

def get_nav_wealthx(code):
    for symbol in get_code_variations(code):
        try:
            url = f"https://www.wealthx.co/funds/{symbol}"
            res = requests.get(url, headers=HEADERS, timeout=8)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                text = soup.get_text()
                match = re.search(r'มูลค่าหน่วยลงทุน\s*\(NAV\)\s*(\d+\.\d{4})', text)
                if match:
                    return float(match.group(1))
                matches = re.findall(r'(\d+\.\d{4})', text)
                if matches:
                    return float(matches[0])
        except Exception:
            pass
    return None

def get_nav_finnomena_page(code):
    for symbol in get_code_variations(code):
        try:
            url = f"https://www.finnomena.com/fund/{symbol}"
            res = requests.get(url, headers=HEADERS, timeout=8)
            if res.status_code == 200:
                match = re.search(r'"nav"\s*:\s*([0-9.]+)', res.text)
                if match:
                    return float(match.group(1))
        except Exception:
            pass
    return None

def fetch_nav(code):
    nav = get_nav_wealthx(code)
    if nav:
        return nav, "WealthX"
    nav = get_nav_finnomena_page(code)
    if nav:
        return nav, "Finnomena"
    return None, None

def update_html_nav(content, code, nav):
    """ ค้นหาและแทนที่ currentNav ภายใน Object ของกองทุนนั้นๆ อย่างปลอดภัย """
    escaped_code = re.escape(code)
    
    # กรณี code อยู่ก่อน currentNav ภายใน Object เดียวกัน
    pattern1 = re.compile(
        r"(\{[^{}]*?code\s*:\s*['\"]" + escaped_code + r"['\"][^{}]*?currentNav\s*:\s*)([0-9.]+)",
        re.MULTILINE
    )
    if pattern1.search(content):
        return pattern1.sub(r"\g<1>" + str(nav), content), True

    # กรณี currentNav อยู่ก่อน code ภายใน Object เดียวกัน
    pattern2 = re.compile(
        r"(\{[^{}]*?currentNav\s*:\s*)([0-9.]+)([^{}]*?code\s*:\s*['\"]" + escaped_code + r"['\"][^{}]*?\})",
        re.MULTILINE
    )
    if pattern2.search(content):
        return pattern2.sub(r"\g<1>" + str(nav) + r"\g<3>", content), True

    return content, False

def main():
    print("🚀 เริ่มต้นระบบดึงข้อมูล NAV อัตโนมัติ...")

    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        print("📖 อ่านไฟล์ index.html เรียบร้อย")
    except Exception as e:
        print(f"❌ อ่านไฟล์ index.html ไม่สำเร็จ: {e}")
        return

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
        nav, source = fetch_nav(code)

        if nav is not None:
            new_content, success = update_html_nav(new_content, code, nav)
            if success:
                print(f"  ✅ {code}: NAV = {nav} (อัปเดตลง HTML แล้ว) [จาก {source}]")
                updated_count += 1
            else:
                print(f"  ⚠️ {code}: NAV = {nav} แต่จับคู่ตำแหน่งใน HTML ไม่เจอ")
        else:
            print(f"  ❌ {code}: ไม่พบข้อมูล NAV")

    if updated_count > 0 and new_content != content:
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"🎉 บันทึกข้อมูล NAV ใหม่ลง index.html เรียบร้อย ({updated_count} รายการ)")
    else:
        print("⚠️ ไม่มีข้อมูล NAV ที่อัปเดตเพิ่ม")

if __name__ == '__main__':
    main()
