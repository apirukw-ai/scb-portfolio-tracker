import os
import re
import json
import requests
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

import firebase_admin
from firebase_admin import credentials, db

# ----------------------------------------------------
# 1. ระบบ เชื่อมต่อ Firebase (รองรับทั้ง Local และ GitHub Actions)
# ----------------------------------------------------
db_url = os.environ.get('DB_URL', 'https://scb-e-class-default-rtdb.asia-southeast1.firebasedatabase.app/')
firebase_key_env = os.environ.get('FIREBASE_KEY')

if firebase_key_env:
    try:
        key_dict = json.loads(firebase_key_env)
        if isinstance(key_dict, str):
            key_dict = json.loads(key_dict)
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        print("🔑 เชื่อมต่อ Firebase สำเร็จ (ผ่าน GitHub Secrets)")
    except Exception as e:
        print(f"❌ โหลด FIREBASE_KEY จาก Environment Variable ล้มเหลว: {e}")
elif os.path.exists("serviceAccountKey.json"):
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {'databaseURL': db_url})
    print("🔑 เชื่อมต่อ Firebase สำเร็จ (ผ่านไฟล์ serviceAccountKey.json)")
else:
    print("⚠️ ไม่พบ Credential สำหรับเชื่อมต่อ Firebase")

# ----------------------------------------------------
# 2. ฟังก์ชันดึงค่า NAV จากภายนอก
# ----------------------------------------------------
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7'
}

DEFAULT_SCB_FUNDS = ["SCBWORLD(E)", "SCBNDQ(E)", "SCBS&P500(E)", "SCBAXJ(E)", "SCBSEMI(E)"]

def get_code_variations(code):
    clean = code.strip()
    variations = [clean, clean.replace('(', '').replace(')', ''), clean.replace('(E)', '-E')]
    base_vars = list(variations)
    for v in base_vars:
        variations.extend([v.replace('&', '%26'), v.replace('&', ''), v.replace('&', '-')])
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

# ----------------------------------------------------
# 3. ฟังก์ชันหลักในการอัปเดตพอร์ต
# ----------------------------------------------------
def main():
    print("🚀 เริ่มต้นระบบดึงข้อมูล NAV อัตโนมัติ (SCB Portfolio)...")

    firebase_data = None
    if firebase_admin._apps:
        ref = db.reference('ports/my-scb-port')
        firebase_data = ref.get()

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

    for code in fund_codes:
        print(f"🔍 กำลังดึง NAV ของ: {code} ...")
        nav, source = fetch_nav(code)

        if nav is not None and 0 < nav <= 1000:
            print(f"   ✅ {code}: NAV = {nav} [{source}]")
            updated_count += 1
            for item in updated_funds_list:
                if isinstance(item, dict) and item.get('code') == code:
                    item['currentNav'] = nav
        else:
            print(f"   ❌ {code}: ไม่พบข้อมูล NAV")

    if updated_count > 0 and firebase_admin._apps:
        total_value = 0
        total_cost = 0
        total_daily_profit = 0

        for item in updated_funds_list:
            if isinstance(item, dict):
                units = float(item.get('units', 0))
                nav_val = float(item.get('currentNav', 0))
                cost_val = float(item.get('avgNav', 0))
                
                prev_nav = float(item.get('prevNav', item.get('navYesterday', cost_val)))
                
                total_value += nav_val * units
                total_cost += cost_val * units
                total_daily_profit += (nav_val - prev_nav) * units

        total_profit = total_value - total_cost
        total_profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0

        prev_total_value = total_value - total_daily_profit
        daily_profit_pct = (total_daily_profit / prev_total_value * 100) if prev_total_value > 0 else 0

        # เวลาประเทศไทย UTC+7
        tz_th = timezone(timedelta(hours=7))
        now_th = datetime.now(tz_th)
        now_th_iso = now_th.isoformat()
        now_th_str = now_th.strftime('%d/%m/%Y %H:%M:%S')
        date_str = now_th.strftime("%d/%m/%y")

        # 1. บันทึกข้อมูลกองทุนลง ports/my-scb-port
        db.reference('ports/my-scb-port').set(updated_funds_list)
        
        # 2. บันทึก Summary
        db.reference('scb_summary/current').set({
            'value': total_value,
            'cost': total_cost,
            'profit': total_profit,
            'profitPct': total_profit_pct,
            'dailyProfit': total_daily_profit,
            'dailyProfitPct': daily_profit_pct,
            'updatedAt': now_th_iso,
            'updatedAtStr': now_th_str
        })

        # 3. บันทึก History Snapshot
        ref_history = db.reference('scb_history')
        existing_history = ref_history.get() or []
        if not isinstance(existing_history, list):
            existing_history = []

        history_entry = {
            'date': date_str,
            'val': total_value,
            'profit': total_profit,
            'cost': total_cost,
            'dailyProfit': total_daily_profit,
            'timestamp': now_th_iso
        }

        found = False
        for idx, h in enumerate(existing_history):
            if isinstance(h, dict) and h.get('date') == date_str:
                existing_history[idx] = history_entry
                found = True
                break
        
        if not found:
            existing_history.append(history_entry)

        if len(existing_history) > 60:
            existing_history = existing_history[-60:]

        ref_history.set(existing_history)
        print("   ✅ บันทึก NAV, Summary และ History Snapshot ขึ้น Firebase เรียบร้อยแล้ว")

    print("==============")
    print(f"TOTAL FUNDS = {len(fund_codes)}")
    print(f"UPDATED FUNDS = {updated_count}")
    print("✅ NAV UPDATE COMPLETE")
    print("==============")

if __name__ == '__main__':
    main()
