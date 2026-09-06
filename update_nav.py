import os
import re
import json
import requests
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# ----------------------------------------------------
# 1. ระบบเชื่อมต่อ Supabase
# ----------------------------------------------------
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://iproktvvetsbxxmpptuj.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imlwcm9rdHZ2ZXRzYnh4bXBwdHVqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NzI5NTc0MSwiZXhwIjoyMTAyODcxNzQxfQ.THAP7rEfCRacre7gDGsQxKmjw-DHbUf6kIoimDQl2Wk')

supabase: Client = None

if SUPABASE_KEY:
    try:
        # เชื่อมต่อ Supabase
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("🔑 เชื่อมต่อ Supabase สำเร็จ")
    except Exception as e:
        print(f"❌ โหลด Supabase Client ล้มเหลว: {e}")
else:
    print("⚠️ ไม่พบ SUPABASE_KEY ใน Environment Variable")

# ----------------------------------------------------
# 2. ฟังก์ชันดึงค่า NAV จาก Finnomena Direct API
# ----------------------------------------------------
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}

DEFAULT_SCB_FUNDS = ["SCBWORLD(E)", "SCBNDQ(E)", "SCBS&P500(E)", "SCBAXJ(E)", "SCBSEMI(E)"]

def get_clean_fund_code(code):
    """ แปลงชื่อกองทุนให้ตรงกับรูปแบบที่ API Finnomena ต้องการ """
    clean = code.strip()
    # SCBS&P500E หรือ SCBS&P500(E) -> SCBS&P500(E) / SCBS-P500-E
    return clean

def get_nav_finnomena_api(code):
    """ ดึง NAV โดยตรงผ่าน API ของ Finnomena """
    search_symbols = [
        code,
        code.replace('&', '%26'),
        code.replace('&', '-'),
        code.replace('(E)', '-E'),
        code.replace('(E)', ''),
        code.replace('SCBS&P500E', 'SCBS%26P500(E)'),
        code.replace('SCBS&P500E', 'SCBS-P500-E')
    ]
    
    # ลองค้นหาผ่าน Public API ของ Finnomena
    for symbol in search_symbols:
        try:
            url = f"https://www.finnomena.com/fn3/api/fund/public/v2/funds/nav/latest?fund_symbol={symbol}"
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict) and 'data' in data:
                    nav_val = data['data'].get('nav') or data['data'].get('value')
                    if nav_val:
                        return float(nav_val)
                elif isinstance(data, dict) and 'nav' in data:
                    return float(data['nav'])
        except Exception:
            pass

        # สำรอง: ค้นผ่าน Finnomena Public Fund Page
        try:
            page_url = f"https://www.finnomena.com/fund/{symbol}"
            res_page = requests.get(page_url, headers=HEADERS, timeout=8)
            if res_page.status_code == 200:
                match = re.search(r'"nav"\s*:\s*([0-9.]+)', res_page.text)
                if match:
                    return float(match.group(1))
        except Exception:
            pass

    return None

def fetch_nav(code):
    nav = get_nav_finnomena_api(code)
    if nav:
        return nav, "Finnomena API"
    return None, None
# ----------------------------------------------------
# 3. ฟังก์ชันหลักในการอัปเดตพอร์ต
# ----------------------------------------------------
def main():
    print("🚀 เริ่มต้นระบบดึงข้อมูล NAV อัตโนมัติ (Supabase)...")

    if not supabase:
        print("❌ ไม่สามารถทำงานต่อได้เนื่องจากไม่ได้เชื่อมต่อ Supabase")
        return

    # 1. อ่านข้อมูลกองทุนจาก Supabase (Schema scb, ตาราง ports)
    try:
        response = supabase.schema('scb').table('ports').select('*').execute()
        ports_data = response.data or []
    except Exception as e:
        print(f"❌ อ่านข้อมูลจาก Supabase ports ล้มเหลว: {e}")
        ports_data = []

    fund_codes = [item.get('code') for item in ports_data if isinstance(item, dict) and item.get('code')]

    if not fund_codes:
        fund_codes = DEFAULT_SCB_FUNDS

    fund_codes = list(dict.fromkeys(fund_codes))
    print(f"📊 พบรายการกองทุนทั้งหมด {len(fund_codes)} รายการ: {', '.join(fund_codes)}")

    updated_count = 0

    # 2. วนลูปดึงราคา NAV และอัปเดตกลับลง Supabase
    for code in fund_codes:
        print(f"🔍 กำลังดึง NAV ของ: {code} ...")
        nav, source = fetch_nav(code)

        if nav is not None and 0 < nav <= 1000:
            print(f"   ✅ {code}: NAV = {nav} [{source}]")
            updated_count += 1
            
            # อัปเดตราคา NAV ลงตาราง ports ใน schema scb
            try:
                supabase.schema('scb').table('ports').update({'nav': nav}).eq('code', code).execute()
            except Exception as e:
                print(f"   ❌ อัปเดต NAV สำหรับ {code} ลง Supabase ล้มเหลว: {e}")
        else:
            print(f"   ❌ {code}: ไม่พบข้อมูล NAV")

    # 3. คำนวณภาพรวมสรุปพอร์ตเมื่อดึง NAV สำเร็จ
    if updated_count > 0:
        # อ่านข้อมูลพอร์ตอนใหม่หลังอัปเดต NAV แล้ว
        fresh_ports = supabase.schema('scb').table('ports').select('*').execute().data or []
        
        total_value = 0
        total_cost = 0
        total_daily_profit = 0

        for item in fresh_ports:
            if isinstance(item, dict):
                units = float(item.get('units', 0))
                nav_val = float(item.get('nav', 0))
                cost_val = float(item.get('cost', 0)) # เงินต้นรวม
                
                prev_nav = float(item.get('prev_nav', item.get('nav_yesterday', nav_val)))
                
                total_value += nav_val * units
                total_cost += cost_val
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

        # 4. บันทึกเข้าตาราง scb_summary
        summary_payload = {
            'id': 'current',
            'value': total_value,
            'cost': total_cost,
            'profit': total_profit,
            'profit_pct': total_profit_pct,
            'daily_profit': total_daily_profit,
            'daily_profit_pct': daily_profit_pct,
            'updated_at': now_th_iso,
            'updated_at_str': now_th_str
        }
        try:
            supabase.schema('scb').table('scb_summary').upsert(summary_payload).execute()
        except Exception as e:
            print(f"❌ อัปเดต scb_summary ล้มเหลว: {e}")

        # 5. บันทึก History Snapshot ลงตาราง scb_history
        history_payload = {
            'date': date_str,
            'val': total_value,
            'profit': total_profit,
            'cost': total_cost,
            'daily_profit': total_daily_profit,
            'timestamp': now_th_iso
        }
        try:
            supabase.schema('scb').table('scb_history').upsert(history_payload, on_conflict='date').execute()
            print("   ✅ บันทึก NAV, Summary และ History Snapshot ลง Supabase เรียบร้อยแล้ว")
        except Exception as e:
            print(f"❌ อัปเดต scb_history ล้มเหลว: {e}")

    print("==============")
    print(f"TOTAL FUNDS = {len(fund_codes)}")
    print(f"UPDATED FUNDS = {updated_count}")
    print("✅ NAV UPDATE COMPLETE")
    print("==============")

if __name__ == '__main__':
    main()
