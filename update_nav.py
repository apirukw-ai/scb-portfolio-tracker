import re
import json
import requests
import urllib.parse

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}

def fetch_nav_finnomena(fund_code):
    """ ดึง NAV จาก Finnomena API โดยแปลงสัญลักษณ์พิเศษ (&, (), -) ให้ถูกต้อง """
    clean_code = fund_code.strip()
    
    variations = [
        clean_code,
        clean_code.replace('(E)', '-E'),
        clean_code.replace('-E', '(E)')
    ]
    
    for symbol in variations:
        try:
            # Encode ตัวอักษรพิเศษ เช่น SCBS&P500(E) -> SCBS%26P500%28E%29
            encoded = urllib.parse.quote(symbol, safe='')
            url = f"https://api.finnomena.com/fund/public/v1/fund/nav/latest?fund_symbol={encoded}"
            res = requests.get(url, headers=HEADERS, timeout=8)
            if res.status_code == 200:
                data = res.json()
                if data.get('status') and data.get('data'):
                    nav = data['data'].get('nav') or data['data'].get('value')
                    if nav:
                        return float(nav)
        except Exception:
            pass
    return None

def fetch_nav_finnomena_search(fund_code):
    """ ค้นหากองทุนผ่าน Search API ในกรณีที่ชื่อตรงๆ ไม่เจอ """
    try:
        search_key = fund_code.replace('(E)', '').replace('-E', '').replace('&', ' ').strip()
        encoded_key = urllib.parse.quote(search_key)
        url = f"https://api.finnomena.com/fund/public/v1/fund?search={encoded_key}"
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            data = res.json()
            funds = data.get('data', [])
            for f in funds:
                symbol = f.get('fund_symbol', '')
                if fund_code.upper() in symbol.upper() or symbol.upper() in fund_code.upper():
                    nav = f.get('nav') or f.get('value')
                    if nav:
                        return float(nav)
    except Exception:
        pass
    return None

def main():
    print("🚀 เริ่มต้นระบบดึงข้อมูล NAV อัตโนมัติ (รองรับ SCB Class E)...")

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
        
        # 1. ดึงด้วยวิธี Encode Symbol
        nav = fetch_nav_finnomena(code)
        
        # 2. สำรองด้วย Search API
        if nav is None:
            nav = fetch_nav_finnomena_search(code)

        if nav is not None:
            print(f"  ✅ {code}: NAV ปัจจุบัน = {nav}")
            
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
            print(f"  ❌ {code}: ไม่พบข้อมูล NAV")

    if updated_count > 0 and new_content != content:
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"🎉 บันทึกข้อมูล NAV ใหม่ลง index.html เรียบร้อย ({updated_count} กองทุน)")
    else:
        print("⚠️ ไม่มีข้อมูล NAV ที่อัปเดตเพิ่ม")

if __name__ == '__main__':
    main()
