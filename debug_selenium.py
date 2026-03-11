#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
混合调试脚本：使用 requests 登录，Selenium 捕获网络请求
"""

import sys
import os
import tomllib
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# 设置输出编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 读取配置
with open("config.toml", "rb") as f:
    config = tomllib.load(f)

user = config.get("account", {}).get("username", "")
pwd = config.get("account", {}).get("password", "")
batch_id = config.get("settings", {}).get("jx0502zbid", "")

# 导入 Auth 类处理登录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from svtu_course_selector import Auth

# 使用 requests 登录获取 session
print("=" * 60)
print("Logging in with requests...")
print("=" * 60)

auth = Auth()
cookie = auth.login(user, pwd)
if not cookie:
    print("Login failed!")
    sys.exit(1)
print("Login successful!")

# 获取 requests session 中的 cookies
session_cookies = auth.session.cookies.get_dict()
print(f"Session cookies: {session_cookies}")

# Chrome 选项
chrome_options = Options()
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--window-size=1920,1080")

# 创建 WebDriver
driver = webdriver.Chrome(options=chrome_options)

try:
    print("\n" + "=" * 60)
    print("Selenium - using authenticated session")
    print("=" * 60)

    # 1. 先打开域名以设置 cookie
    print("\n[1] Opening base domain...")
    driver.get("https://jwxt.sztu.edu.cn")
    time.sleep(2)

    # 2. 添加 cookies
    print("\n[2] Adding cookies to browser...")
    for name, value in session_cookies.items():
        driver.add_cookie({
            'name': name,
            'value': value,
            'domain': '.sztu.edu.cn',
            'path': '/'
        })
        print(f"   Added cookie: {name}")

    # 3. 直接访问"专业内跨年级选课"页面
    print("\n[3] Accessing 专业内跨年级选课 page...")
    page_url = f"https://jwxt.sztu.edu.cn/jsxsd/xsxk/xsxkZynknjxk?jx0502zbid={batch_id}"
    print(f"   URL: {page_url}")
    driver.get(page_url)
    time.sleep(5)

    print(f"   Page title: {driver.title}")
    print(f"   Page URL: {driver.current_url}")

    # 4. 保存页面 HTML
    html = driver.page_source
    with open("debug_page_zynknjxk.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[4] HTML saved: {len(html)} chars -> debug_page_zynknjxk.html")

    print("\n   Page HTML preview (first 800 chars):")
    preview = html[:800].replace("\n", " ")
    print(f"   {preview[0]}")

    # 5. 查找页面元素
    print("\n[5] Analyzing page elements...")

    forms = driver.find_elements(By.TAG_NAME, "form")
    print(f"   Forms: {len(forms)}")
    for i, form in enumerate(forms[:3]):
        print(f"      Form {i}: action={form.get_attribute('action')}")

    buttons = driver.find_elements(By.TAG_NAME, "button")
    print(f"   Buttons: {len(buttons)}")
    for i, btn in enumerate(buttons[:8]):
        print(f"      Button {i}: text={btn.text[:20]}, type={btn.get_attribute('type')}")

    inputs = driver.find_elements(By.TAG_NAME, "input")
    print(f"   Inputs: {len(inputs)}")
    for i, inp in enumerate(inputs[:15]):
        print(f"      Input {i}: name={inp.get_attribute('name')}, value={inp.get_attribute('value')}, type={inp.get_attribute('type')}")

    # 6. 点击搜索按钮
    print("\n[6] Clicking search button...")

    # 尝试多种方式查找搜索按钮
    found = False
    for i, btn in enumerate(buttons):
        text = btn.text.strip()
        if '查询' in text or '搜索' in text or 'Query' in text.lower():
            print(f"   Found search button: {text}")
            driver.execute_script("arguments[0].click();", btn)
            found = True
            time.sleep(5)
            break

    if not found:
        # 尝试通过 input 查找
        for i, inp in enumerate(inputs):
            value = inp.get_attribute('value') or ''
            if '查询' in value or '搜索' in value:
                print(f"   Found search input: {value}")
                driver.execute_script("arguments[0].click();", inp)
                found = True
                time.sleep(5)
                break

    if not found:
        print("   Search button not found!")
        print("   Trying to click first button...")
        if buttons:
            driver.execute_script("arguments[0].click();", buttons[0])
            time.sleep(5)

    # 7. 保存最终页面
    final_html = driver.page_source
    with open("debug_page_zynknjxk_after_search.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    print(f"\n[7] Final HTML saved: {len(final_html)} chars -> debug_page_zynknjxk_after_search.html")

    # 8. 检查页面内容
    print("\n[8] Page content analysis:")
    if 'aaData' in final_html:
        print("   Found 'aaData' (embedded JSON)")
    if '课程' in final_html:
        print("   Found '课程' (course data)")
    if '错误' in final_html or 'error' in final_html.lower():
        print("   Found error indicators")
    if 'jx0404id' in final_html:
        print("   Found 'jx0404id' (course IDs)")

    # 9. 测试"跨专业选课"
    print("\n[9] Testing 跨专业选课...")
    print("   Browser will stay open, please manually navigate and click search.")
    print("   This will run for 120 seconds to allow manual inspection.")

    time.sleep(120)

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
    time.sleep(30)

finally:
    driver.quit()
    print("\nBrowser closed")
