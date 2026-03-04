import json
import sys
import os
import requests
import time
import tomllib

# Add current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from sztu_course_selector import Auth, user, pwd
except ImportError:
    print("Error: Could not import Auth from sztu_course_selector.")
    sys.exit(1)

# 从 config.toml 读取批次 ID
try:
    with open('config.toml', 'rb') as f:
        config_toml = tomllib.load(f)
    JX0502ZBID = config_toml.get('settings', {}).get('jx0502zbid', '')
except FileNotFoundError:
    print("❌ 找不到配置文件 config.toml")
    sys.exit(1)
except Exception as e:
    print(f"❌ 读取 config.toml 失败: {e}")
    sys.exit(1)

if not JX0502ZBID or '请' in JX0502ZBID or 'XXXX' in JX0502ZBID:
    print("❌ 请先在 config.toml 中 [settings] 节点下填写有效的 jx0502zbid（批次 ID）")
    sys.exit(1)

def fetch_courses_from_url(auth, url, data_list, label):
    print(f"📥 Fetching {label}...")
    for attempt in range(1, 4):
        try:
            resp = auth.post(url, data=data_list)
            if "My JSP" in resp.text:
                print(f"   ⚠️ Server returned JSP placeholder for {label}.")
                return []
            
            try:
                res_json = resp.json()
            except:
                if "错误" in resp.text:
                    print(f"   ❌ Server returned Error Page for {label} (Attempt {attempt}/3).")
                else:
                    print(f"   ❌ Response is not JSON from {label} (Attempt {attempt}/3).")
                if attempt < 3: time.sleep(5)
                continue

            if 'aaData' in res_json:
                count = len(res_json['aaData'])
                print(f"   ✅ {label}: Found {count} courses.")
                return res_json['aaData']
            else:
                print(f"   ⚠️ No 'aaData' in response from {label}.")
                return []
        except Exception as e:
            print(f"   ❌ Error fetching {label} (Attempt {attempt}/3): {e}")
            if attempt < 3: time.sleep(5)
    return []

def fetch_and_save_courses():
    print(f"🚀 Starting crawler with batch ID: {JX0502ZBID}")
    
    auth = Auth()
    print("🔐 Logging in...")
    cookie = auth.login(user, pwd)
    if not cookie:
        print("❌ Login failed.")
        return
    print("✅ Login successful.")

    # 1. Check-in
    index_url = f'https://jwxt.sztu.edu.cn/jsxsd/xsxk/xsxk_index?jx0502zbid={JX0502ZBID}'
    auth.get(index_url)
    print("➡️ Check-in complete.")

    all_courses = []

    # Common payload structure
    base_data = {
        "sEcho": 1,
        "iColumns": 15,
        "sColumns": "",
        "iDisplayStart": 0,
        "iDisplayLength": 10000, # Large limit
        "mDataProp_0": "kch",
    }
    # Fill defaults
    for i in range(1, 15):
        base_data[f"mDataProp_{i}"] = "test"

    # 2. Plan Selection (Bxqjhxk)
    url_bx = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkBxqjhxk?kcxx=&skls=&skxq=&skjc=&sfym=false&sfct=true&sfxx=true&skfs="
    # Bxqjhxk specific props if needed, but defaults usually work or are ignored
    courses_bx = fetch_courses_from_url(auth, url_bx, base_data, "Plan Selection")
    all_courses.extend(courses_bx)

    # 3. Cross-Grade/General Selection (Knjxk)
    url_kn = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkKnjxk?kcxx=&skls=&skxq=&skjc=&endJc=&sfym=false&sfct=true&sfxx=true&skfs="
    courses_kn = fetch_courses_from_url(auth, url_kn, base_data, "Cross-Grade Selection")
    all_courses.extend(courses_kn)
    
    # 4. Public Electives (Ggxxkxk)
    url_gg = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkGgxxkxk?kcxx=&skls=&skxq=&skjc=&sfym=false&sfct=true&sfxx=true&skfs="
    courses_gg = fetch_courses_from_url(auth, url_gg, base_data, "Public Electives")
    all_courses.extend(courses_gg)

    # 5. Experiment Selection (Syxk)
    url_sy = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkSyxk?kcxx=&skls=&skxq=&skjc=&sfym=false&sfct=true&sfxx=true&skfs="
    courses_sy = fetch_courses_from_url(auth, url_sy, base_data, "Experiment Selection")
    all_courses.extend(courses_sy)

    print(f"📊 Total unique courses found: {len(all_courses)}")
    
    if all_courses:
        output_file = "选课数据.json"
        with open(output_file, "w", encoding='utf-8') as f:
            json.dump(all_courses, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved data to {output_file}")
    else:
        print("⚠️ No data found in any category. The batch may be closed or empty.")

if __name__ == "__main__":
    fetch_and_save_courses()
