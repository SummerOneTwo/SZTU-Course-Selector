import time
import re
import sys
import subprocess
from sztu_course_selector import Auth, user, pwd, conf

# Force UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Known IDs to ignore (e.g., the current Lottery ID)
KNOWN_IDS = [
    '07D603B744494337B533D3183C386091', # Current Lottery (Plan)
]

def update_config(new_id):
    print(f"💾 Updating config.txt with new ID: {new_id}")
    try:
        with open('config.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        with open('config.txt', 'w', encoding='utf-8') as f:
            for line in lines:
                if line.strip().startswith('jx0502zbid') and '=' in line:
                    # Comment out old active line
                    if not line.strip().startswith('#'):
                        f.write(f"# {line}") 
                        f.write(f"jx0502zbid = {new_id}\n")
                    else:
                        f.write(line)
                else:
                    f.write(line)
        print("✅ Config updated successfully.")
        return True
    except Exception as e:
        print(f"❌ Failed to update config: {e}")
        return False

def monitor():
    print("🚀 Starting Batch ID Monitor...")
    auth = Auth()
    if not auth.login(user, pwd):
        print("❌ Login failed.")
        return

    print("✅ Login successful. Monitoring started.")
    print(f"ℹ️  Ignoring known ID: {KNOWN_IDS[0][:8]}...")
    print("⏳ Waiting for new Batch ID to appear (Refresh every 2s)...")

    url = 'https://jwxt.sztu.edu.cn/jsxsd/xsxk/xsxk_index'
    
    while True:
        try:
            # Request the course selection index
            resp = auth.get(url)
            
            # Find all potential 32-char hex IDs
            found_ids = re.findall(r'jx0502zbid=([A-Fa-f0-9]{32})', resp.text)
            
            new_id_found = None
            for fid in found_ids:
                if fid not in KNOWN_IDS:
                    new_id_found = fid
                    break
            
            if new_id_found:
                print("\n" + "!"*50)
                print(f"🚨 NEW BATCH ID FOUND: {new_id_found}")
                print("!"*50)
                
                # 1. Update Config
                if update_config(new_id_found):
                    # 2. Launch Selector Immediately
                    print("\n🚀 Launching Course Selector NOW...")
                    subprocess.run(["run.bat"], shell=True)
                    break
                else:
                    print("⚠️  Config update failed. Please manually update and run.")
                    break
            else:
                current_time = time.strftime("%H:%M:%S", time.localtime())
                print(f"\r[{current_time}] No new ID found yet...", end="")
                
            time.sleep(2)
            
        except Exception as e:
            print(f"\n❌ Error during check: {e}")
            time.sleep(5) # Wait longer on error

if __name__ == "__main__":
    monitor()
