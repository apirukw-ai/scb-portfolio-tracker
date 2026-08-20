import requests
from bs4 import BeautifulSoup
import re

# URL Firebase Realtime Database ของคุณ
FIREBASE_DB_URL = "https://scb-e-class-default-rtdb.asia-southeast1.firebasedatabase.app"
SYNC_ID = "my-scb-port"

def fetch_scbam_navs():
    nav_data = {}
    try:
        url = "https://www.scbam.com/th/fund/nav"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    fund_code = cols[0].get_text(strip=True).upper()
                    clean_code = re.sub(r'[^A-Z0-9]', '', fund_code)
                    nav_str = cols[1].get_text(strip=True).replace(',', '')
                    change_str = cols[2].get_text(strip=True).replace(',', '').replace('%', '').replace('+', '')
                    
                    try:
                        nav_val = float(nav_str)
                        change_val = float(change_str) if change_str else 0.0
                        nav_data[clean_code] = {'nav': nav_val, 'change_pct': change_val}
                    except ValueError:
                        continue
    except Exception as e:
        print(f"Error fetching SCBAM NAVs: {e}")
    return nav_data

def main():
    print("Starting Automated NAV Update...")
    fb_url = f"{FIREBASE_DB_URL.rstrip('/')}/ports/{SYNC_ID}.json"
    
    # 1. ดึงข้อมูลพอร์ตปัจจุบันจาก Firebase
    res = requests.get(fb_url)
    if res.status_code != 200 or not res.json():
        print("Failed to fetch data from Firebase.")
        return

    funds = res.json()
    scbam_navs = fetch_scbam_navs()
    updated = False

    # 2. จับคู่ชื่อกองทุนและอัปเดต NAV + % รายวัน
    for fund in funds:
        code_raw = fund.get('code', '').upper()
        code_clean = re.sub(r'[^A-Z0-9]', '', code_raw)
        
        if code_clean in scbam_navs:
            new_nav = scbam_navs[code_clean]['nav']
            new_pct = scbam_navs[code_clean]['change_pct']
            
            print(f"Updated {code_raw}: NAV {fund.get('currentNav')} -> {new_nav} | Change: {new_pct}%")
            fund['currentNav'] = new_nav
            fund['dailyPct'] = new_pct
            updated = True

    # 3. ส่งข้อมูล NAV ล่าสุดกลับไปยัง Firebase
    if updated:
        put_res = requests.put(fb_url, json=funds)
        if put_res.status_code == 200:
            print("Successfully updated Firebase Realtime Database!")
        else:
            print(f"Firebase Update Error: {put_res.status_code}")

if __name__ == "__main__":
    main()
