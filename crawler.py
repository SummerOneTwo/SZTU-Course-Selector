#!/usr/bin/env python3
"""
SZTU 课程数据完整爬虫 V3 - Final
功能：抓取所有选课类型的完整课程数据（包括已满、冲突、限选）
作者：Sisyphus
日期：2026-03-11

更新记录：
- V3: 添加7种选课类型，抓取全部课程数据，不覆盖原有数据
"""

import json
import sys
import os
import time
import tomllib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from sztu_course_selector import Auth, user, pwd
except ImportError as e:
    print(f"错误: 无法导入 Auth - {e}")
    sys.exit(1)

total_stats = {}


def get_batch_id():
    with open("config.toml", "rb") as f:
        config = tomllib.load(f)
    bid = config.get("settings", {}).get("jx0502zbid", "")
    if not bid:
        print("错误: 批次ID无效")
        sys.exit(1)
    return bid


def fetch_courses(auth, url, data, label):
    print(f"\n📥 {label}")

    for attempt in range(1, 4):
        try:
            resp = auth.post(url, data=data)

            if "My JSP" in resp.text:
                print(f"   ⚠️ JSP 占位符")
                return []

            try:
                res_json = resp.json()
            except json.JSONDecodeError:
                print(f"   ❌ 非JSON响应 (attempt {attempt})")
                if attempt < 3:
                    time.sleep(2)
                continue

            if "aaData" in res_json:
                courses = res_json["aaData"]

                seen = set()
                unique = []
                for c in courses:
                    jx_id = c.get("jx0404id", "")
                    if jx_id and jx_id not in seen:
                        seen.add(jx_id)
                        c["_course_type"] = label
                        unique.append(c)

                total_stats[label] = len(unique)
                print(f"   ✅ {len(unique)} 门课程")
                return unique
            else:
                print(f"   ⚠️ 无 aaData 字段")
                return []

        except Exception as e:
            print(f"   ❌ 错误 (attempt {attempt}): {e}")
            if attempt < 3:
                time.sleep(3)

    return []


def build_url(endpoint):
    base = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc"

    # 关键参数: sfym=false 显示已满, sfct=false 显示冲突, sfxx=false 显示限选
    params = {
        "kcxx": "",
        "skls": "",
        "skxq": "",
        "skjc": "",
        "sfym": "false",
        "sfct": "false",
        "sfxx": "false",
        "skfs": "",
    }

    if endpoint == "xsxkKnjxk":
        params["endJc"] = ""

    query = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"{base}/{endpoint}?{query}"


def main():
    start = time.time()

    print("=" * 60)
    print("🎓 SZTU 完整课程数据爬虫 V3")
    print("=" * 60)
    print(f"开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    batch_id = get_batch_id()
    print(f"\n🆔 批次 ID: {batch_id}")

    print("\n🔐 登录中...")
    auth = Auth()
    cookie = auth.login(user, pwd)
    if not cookie:
        print("❌ 登录失败")
        sys.exit(1)
    print("✅ 登录成功")

    print("\n➡️ 进入选课系统...")
    auth.get(f"https://jwxt.sztu.edu.cn/jsxsd/xsxk/xsxk_index?jx0502zbid={batch_id}")
    print("✅ 已进入")

    base_data = {
        "sEcho": 1,
        "iColumns": 15,
        "sColumns": "",
        "iDisplayStart": 0,
        "iDisplayLength": 10000,
        "mDataProp_0": "kch",
    }
    for i in range(1, 15):
        base_data[f"mDataProp_{i}"] = "test"

    # 7种选课类型
    course_types = [
        ("xsxkBxqjhxk", "本学期计划选课"),
        ("xsxkKnjxk", "跨年级选课"),
        ("xsxkGgxxkxk", "公选课选课"),
        ("xsxkSyxk", "实验选课"),
        ("xsxkZynknjxk", "专业内跨年级选课"),
        ("xsxkKzyxkkc", "跨专业选课"),
        ("xsxkFawxk", "跨专业选课(FA)"),
    ]

    all_courses = []

    print("\n" + "=" * 60)
    print("📚 开始抓取各类型课程数据")
    print("=" * 60)

    for endpoint, label in course_types:
        url = build_url(endpoint)
        courses = fetch_courses(auth, url, base_data, label)

        if courses:
            all_courses.extend(courses)
            print(f"   📊 累计: {len(all_courses)} 门")

        time.sleep(0.5)

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print("📊 抓取完成统计")
    print("=" * 60)
    print(f"⏱️  总耗时: {elapsed:.2f} 秒")
    print(f"📚 总课程: {len(all_courses)} 门")
    print("\n各类型分布:")
    for label, count in total_stats.items():
        print(f"  - {label}: {count} 门")
    print("=" * 60)

    if all_courses:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 保存带时间戳的版本（不覆盖任何数据）
        filename_ts = f"选课数据_完整_{timestamp}.json"
        with open(filename_ts, "w", encoding="utf-8") as f:
            json.dump(all_courses, f, ensure_ascii=False, indent=2)

        # 保存最新版本（便于对比）
        filename_latest = "选课数据_完整_最新.json"
        with open(filename_latest, "w", encoding="utf-8") as f:
            json.dump(all_courses, f, ensure_ascii=False, indent=2)

        print(f"\n💾 数据已保存:")
        print(f"  {filename_ts}")
        print(f"  {filename_latest}")
        print(f"\n📊 对比提示:")
        print(f"  - 旧数据: 选课数据.json (如果存在)")
        print(f"  - 新数据: {filename_ts}")
    else:
        print("\n⚠️ 未抓取到数据")

    print("\n" + "=" * 60)
    print("✅ 爬虫执行完毕")
    print("=" * 60)


if __name__ == "__main__":
    main()
