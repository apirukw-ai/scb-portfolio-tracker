import os
import re
import requests
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime

# 📍 1. แทรกส่วนเชื่อมต่อ Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, db

# ตรวจสอบและเชื่อมต่อ Firebase ผ่านไฟล์ serviceAccountKey.json หรือ Secret
FIREBASE_SECRET = os.environ.get('FIREBASE_SECRET')

if os.path.exists("serviceAccountKey.json"):
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://scb-e-class-default-rtdb.asia-southeast1.firebasedatabase.app/'
    })
    print("🔑 เชื่อมต่อ Firebase Admin SDK สำเร็จ (serviceAccountKey)")
else:
    print("⚠️ ไม่พบไฟล์ serviceAccountKey.json (ใช้ระบบ REST API Backup)")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7'
}

# รายการกองทุน SCB e-Class สำรองกรณี Cloud ว่างเปล่า
DEFAULT_SCB_FUNDS = [
    "SCBWORLD(E)",
    "SCBNDQ(E)",
    "SCBS&P500(E)",
    "SCBAXJ(E)",
    "SCBSEMI(E)"
]

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

def main():
    print("🚀 เริ่มต้นระบบดึงข้อมูล NAV อัตโนมัติ (SCB Portfolio)...")

    # 📖 ดึงข้อมูลรายการกองทุนสดจาก Firebase Cloud โดยตรง
    firebase_data = None
    if firebase_admin._apps:
        ref = db.reference('ports/my-scb-port')
        firebase_data = ref.get()
    else:
        FIREBASE_URL = "https://scb-e-class-default-rtdb.asia-southeast1.firebasedatabase.app/ports/my-scb-port.json"
        try:
            res = requests.get(FIREBASE_URL, timeout=10)
            if res.status_code == 200:
                firebase_data = res.json()
        except Exception as e:
            print(f"⚠️ Fetch Firebase Error: {e}")

    # ดึงรายชื่อกองทุนจาก Cloud หรือใช้ Default
    fund_codes = []
    if firebase_data and isinstance(firebase_data, list):
        for item in firebase_data:
            if isinstance(item, dict) and item.get('code'):
                fund_codes.append(item.get('code'))
    
    if not fund_codes:
        fund_codes = DEFAULT_SCB_FUNDS

    fund_codes = list(dict.fromkeys(fund_codes))
    print(f"📊 พบรายการกองทุนทั้งหมด {len(fund_codes)} รายการ: {', '.join(fund_codes)}")

    updated_count = 0
    updated_funds_list = firebase_data if (firebase_data and isinstance(firebase_data, list)) else []

    # วนลูปดึง NAV
    for code in fund_codes:
        print(f"🔍 กำลังดึง NAV ของ: {code} ...")
        nav, source = fetch_nav(code)

        if nav is not None and 0 < nav <= 1000:
            print(f"   ✅ {code}: NAV = {nav} [{source}]")
            updated_count += 1
            
            # อัปเดตใส่โครงสร้างอาร์เรย์
            for item in updated_funds_list:
                if isinstance(item, dict) and item.get('code') == code:
                    item['currentNav'] = nav
        else:
            print(f"   ❌ {code}: ไม่พบข้อมูล NAV หรือค่า NAV ไม่ถูกต้อง")

    # ☁️ บันทึกค่าขึ้น Firebase Cloud
    if updated_count > 0:
        total_value = 0
        total_cost = 0

        for item in updated_funds_list:
            if isinstance(item, dict):
                units = item.get('units', 0)
                nav_val = item.get('currentNav', 0)
                cost_val = item.get('avgNav', 0)
                total_value += nav_val * units
                total_cost += cost_val * units

        total_profit = total_value - total_cost
        total_profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0

        if firebase_admin._apps:
            # 1. บันทึกข้อมูลพอร์ต
            db.reference('ports/my-scb-port').set(updated_funds_list)
            # 2. บันทึก Summary
            db.reference('scb_summary/current').set({
                'value': total_value,
                'cost': total_cost,
                'profit': total_profit,
                'profitPct': total_profit_pct,
                'updatedAt': datetime.now().isoformat()
            })
            print("  ✅ อัปเดต NAV และ Summary ขึ้น Firebase Cloud ผ่าน Admin SDK เรียบร้อยแล้ว")
        else:
            # สำรองผ่าน REST API
            FIREBASE_URL = "https://scb-e-class-default-rtdb.asia-southeast1.firebasedatabase.app/ports/my-scb-port.json"
            param = f"?auth={FIREBASE_SECRET}" if FIREBASE_SECRET else ""
            requests.put(FIREBASE_URL + param, json=updated_funds_list)
            print("  ✅ อัปเดต NAV ใหม่ขึ้น Firebase Cloud เรียบร้อยแล้ว")

    print("==============")
    print(f"TOTAL FUNDS = {len(fund_codes)}")
    print(f"UPDATED FUNDS = {updated_count}")
    print("✅ NAV UPDATE COMPLETE")
    print("==============")

if __name__ == '__main__':
    main()
