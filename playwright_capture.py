import sys
import time
import tomllib
from playwright.sync_api import sync_playwright

def get_config():
    with open("c:/userProgram/program/SZTU-Course-Selector/config.toml", "rb") as f:
        config = tomllib.load(f)
    user = config.get("account", {}).get("username", "")
    pwd = config.get("account", {}).get("password", "")
    batch_id = config.get("settings", {}).get("jx0502zbid", "")
    return user, pwd, batch_id

def run():
    user, pwd, batch_id = get_config()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        log_file = open("C:/Users/User/temp/network_log.txt", "w", encoding="utf-8")
        def log(msg):
            print(msg)
            log_file.write(msg + "\n")
            log_file.flush()

        log("Logging in...")
        page.goto("https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu")
        page.fill("input#j_username", user)
        page.fill("input#j_password", pwd)
        page.click("button#loginButton")
        page.wait_for_url("https://jwxt.sztu.edu.cn/**", timeout=15000)
        log("Login successful.")

        index_url = f"https://jwxt.sztu.edu.cn/jsxsd/xsxk/xsxk_index?jx0502zbid={batch_id}"
        log(f"Navigating to index: {index_url}")
        page.goto(index_url)
        page.wait_for_load_state("networkidle")

        def handle_response(response):
            if "xsxkkc" in response.url or "xsxk" in response.url:
                try:
                    if response.request.method == "POST":
                        log(f"\n[POST] URL: {response.url}")
                        log(f"Payload: {response.request.post_data}")
                        body = response.text()
                        log(f"Response: {body[:300]}...")
                    elif response.request.resource_type in ["xhr", "fetch"]:
                        log(f"\n[GET/XHR] URL: {response.url}")
                except Exception as e:
                    pass
        
        page.on("response", handle_response)

        log("\nClicking '专业内跨年级选课' tab...")
        try:
            page.locator("text=专业内跨年级选课").click(timeout=5000)
            page.wait_for_load_state("networkidle")
            time.sleep(3)
        except Exception as e:
            log(f"Failed to click tab: {e}")

        log("\nClicking '跨专业选课' tab...")
        try:
            page.locator("text=跨专业选课").click(timeout=5000)
            page.wait_for_load_state("networkidle")
            time.sleep(3)
        except Exception as e:
            log(f"Failed to click tab: {e}")

        browser.close()
        log_file.close()

if __name__ == "__main__":
    run()
