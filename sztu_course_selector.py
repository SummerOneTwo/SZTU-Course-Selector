import base64
import json
import os
import sys
import time
import traceback
import requests
import threading
import random
import datetime
import tomllib
from Crypto.Cipher import DES
import urllib3
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor
import ctypes  # 用于调用 Windows 消息框提示
# 强制 stdout 使用 utf-8 编码，防止 Windows 下打印 Emoji 报错
sys.stdout.reconfigure(encoding='utf-8')

# 禁用InsecureRequestWarning警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SessionExpiredError(Exception):
    pass

session_expired = False

# --- 1. 配置加载与校验 ---
try:
    with open('config.toml', 'rb') as f:
        config = tomllib.load(f)
    
    user = config['account']['username']
    pwd = config['account']['password']
    
    courses_config = []
    for c in config.get('courses', []):
        kcid = c['kcid'].strip()
        cno = str(c.get('cno', '0')).strip()
        jx_items = c.get('jx0404id', [])
        if isinstance(jx_items, str):
            jx_items = [x.strip() for x in jx_items.split(',') if x.strip()]
        else:
            jx_items = [str(x).strip() for x in jx_items if str(x).strip()]
            
        courses_config.append({
            'kcid': kcid,
            'cno': cno,
            'jx_list': jx_items,
            'name': c.get('name', '未命名课程')
        })
        
    settings = config.get('settings', {})
    run_mode = settings.get('mode', 'monitor').strip().lower()
    target_count = settings.get('target_count', 1)
    jx0502zbid = settings.get('jx0502zbid', '')
    max_workers = settings.get('max_workers', 8)
    round_cool_down_min = settings.get('round_cool_down_min', 30)
    round_cool_down_max = settings.get('round_cool_down_max', 90)
    schedule_start = settings.get('schedule_start', '08:55')
    schedule_end = settings.get('schedule_end', '22:00')

    if run_mode == 'monitor':
        REQ_TIMEOUT = (3, 5) # 首发模式：连接3s，读取5s
        retry_min, retry_max = 1, 3 # 极速重试
    else:
        REQ_TIMEOUT = (5, 10) # 捡漏模式：连接5s，读取10s
        retry_min, retry_max = round_cool_down_min, round_cool_down_max

except FileNotFoundError:
    print("❌ 找不到配置文件 config.toml")
    print("请复制 config.toml.example 并重命名为 config.toml 进行配置。")
    input("按回车键退出...")
    sys.exit(1)
except Exception as e:
    print(f"❌ 读取配置文件失败: {e}")
    print("请确保 config.toml 格式正确。")
    input("按回车键退出...")
    sys.exit(1)

def is_in_time_window(start_str, end_str):
    """当前是否在运行时间窗口内。窗口外返回到下次开始的秒数，窗口内返回0。"""
    now = datetime.datetime.now()
    current_time = now.time()
    try:
        start_time = datetime.datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.datetime.strptime(end_str, "%H:%M").time()
    except ValueError:
        return 0
        
    if start_time <= current_time <= end_time:
        return 0
        
    next_start = now.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
    if current_time > end_time:
        next_start += datetime.timedelta(days=1)
        
    delta = (next_start - now).total_seconds()
    return delta if delta > 0 else 0

def pad(data, block_size=8):
    length = block_size - (len(data) % block_size)
    return data.encode(encoding='utf-8') + (chr(length) * length).encode(encoding='utf-8')

# ==============================================================================
#  Auth 类 - 严格保留，仅将硬编码的jx0502zbid改为参数
# ==============================================================================
class Auth:
    cookies = {}
    ok = False

    def __init__(self, cookies=None):
        self.session = requests.session()
        
        retry_strategy = Retry(total=3, connect=3, backoff_factor=0.1)
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ' \
                                             'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36'
        self.session.headers['Host'] = 'auth.sztu.edu.cn'
        self.session.headers['Referer'] = 'https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu'
        self.session.headers['Origin'] = 'https://auth.sztu.edu.cn'
        self.session.headers['X-Requested-With'] = 'XMLHttpRequest'
        self.session.headers['Sec-Fetch-Site'] = 'same-origin'
        self.session.headers['Sec-Fetch-Mode'] = 'cors'
        self.session.headers['Sec-Fetch-Dest'] = 'empty'
        self.session.headers['sec-ch-ua-mobile'] = '?0'
        self.session.headers['sec-ch-ua-platform'] = '"macOS"'
        self.session.headers['sec-ch-ua'] = '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"'
        self.session.headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        if cookies:
            self.session.cookies = requests.utils.cookiejar_from_dict(cookies)
            self.check_login()

    def login(self, school_id, password):
        # 登录逻辑完全保持不变
        self.session.headers['Host'] = 'jwxt.sztu.edu.cn'
        resp = self.get('https://jwxt.sztu.edu.cn/')
        resp = self.get(resp.headers['Location'])
        resp = self.get(resp.headers['Location'])
        self.session.headers['Host'] = 'auth.sztu.edu.cn'
        self.get(resp.headers['Location'])
        self.get('https://auth.sztu.edu.cn/idp/AuthnEngine')
        self.get('https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu')
        data = {
            'j_username': school_id,
            'j_password': self.encryptByDES(password),
            'j_checkcode': '验证码', 'op': 'login',
            'spAuthChainCode': 'cc2fdbc3599b48a69d5c82a665256b6b'
        }
        resp = self.post('https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain', data)
        resp_json = resp.json()
        if resp_json.get('loginFailed') != 'false':
            return {}, False
        resp = self.post('https://auth.sztu.edu.cn/idp/AuthnEngine?currentAuth=urn_oasis_names_tc_SAML_2.0_ac_classes_BAMUsernamePassword', data=data)
        ssoURL = resp.headers['Location']
        resp = self.get(ssoURL)
        logonUrl = resp.headers['Location']
        self.session.headers['Host'] = 'jwxt.sztu.edu.cn'
        resp = self.get(logonUrl)
        oldCookie = self.session.cookies.get_dict()['JSESSIONID']
        loginToTkUrl = resp.headers['Location']
        self.get(loginToTkUrl)
        self.get('https://jwxt.sztu.edu.cn/jsxsd/framework/xsMain.htmlx')
        self.cookies = self.session.cookies.get_dict()
        self.check_login()
        mycookie = f"JSESSIONID={oldCookie};JSESSIONID={self.cookies['JSESSIONID']};SERVERID={self.cookies['SERVERID']}"
        return mycookie

    @staticmethod
    def encryptByDES(message, key='PassB01Il71'):
        key1 = key.encode('utf-8')[:8]
        cipher = DES.new(key=key1, mode=DES.MODE_ECB)
        encrypted_text = cipher.encrypt(pad(message, block_size=8))
        return base64.b64encode(encrypted_text).decode('utf-8')

    def check_login(self):
        resp = self.get('https://jwxt.sztu.edu.cn/jsxsd/framework/xsMain.htmlx')
        self.ok = (resp.status_code == 200)

    def get(self, url):
        return self.session.get(url, timeout=REQ_TIMEOUT, verify=False, allow_redirects=False)

    def post(self, url, data):
        return self.session.post(url, timeout=REQ_TIMEOUT, verify=False, data=data, allow_redirects=False)

    def logintoXK(self, cno):
        print("➡️ 正在进入选课系统...")
        url = f'https://jwxt.sztu.edu.cn/jsxsd/xsxk/xsxk_index?jx0502zbid={jx0502zbid}'
        self.get(url)
        if cno == "0":
            url_list = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkBxqjhxk?kcxx=&skls=&skxq=&skjc=&sfym=false&sfct=true&sfxx=true&skfs="
            data_list = "sEcho=1&iColumns=13&sColumns=&iDisplayStart=0&iDisplayLength=15&mDataProp_0=kch&mDataProp_1=kczh&mDataProp_2=kcmc&mDataProp_3=xf&mDataProp_4=skls&mDataProp_5=sksj&mDataProp_6=skdd&mDataProp_7=xqmc&mDataProp_8=syzxwrs&mDataProp_9=syfzxwrs&mDataProp_10=ctsm&mDataProp_11=szkcflmc&mDataProp_12=czOper"
        else:
            url_list = "https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/xsxkKnjxk?kcxx=&skls=&skxq=&skjc=&endJc=&sfym=false&sfct=true&sfxx=true&skfs="
            data_list = "sEcho=1&iColumns=15&sColumns=&iDisplayStart=0&iDisplayLength=15&mDataProp_0=kch&mDataProp_1=kczh&mDataProp_2=kcmc&mDataProp_3=zyfxmc&mDataProp_4=fzmc&mDataProp_5=xf&mDataProp_6=skls&mDataProp_7=sksj&mDataProp_8=skdd&mDataProp_9=xqmc&mDataProp_10=xkrs&mDataProp_11=syzxwrs&mDataProp_12=syfzxwrs&mDataProp_13=ctsm&mDataProp_14=czOper"
        self.post(url_list, data=data_list)
        print("✅ 已进入选课界面。")

    def get_course(self, kcid, jxid, cno):
        if cno == "0":
            url = f"https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/bxqjhxkOper?kcid={kcid}&cfbs=null&jx0404id={jxid}&xkzy=&trjf="
        else:
            url = f"https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/knjxkOper?kcid={kcid}&cfbs=null&jx0404id={jxid}&xkzy=&trjf="
        return self.get(url)

def select_course_worker(auth_session, kc, jx, cno, name="未命名课程"):
    """单课程选课工作函数，首发模式最多重试3次，捡漏模式1次。"""
    global session_expired
    tag = name  # 日志标签使用课程名
    max_attempts = 3 if run_mode == 'monitor' else 1

    for attempt in range(max_attempts):
        if session_expired:
            return False, (kc, jx, cno)
        try:
            # 首发模式：重试时短暂等待；捡漏模式/首次请求：不等待
            if attempt > 0:
                time.sleep(0.3)

            res = auth_session.get_course(kc, jx, cno)

            if "登录" in res.text or "idp" in res.url or res.status_code == 302:
                session_expired = True
                print(f"⚠️ [{tag}] 会话过期！")
                return False, (kc, jx, cno)

            try:
                message = res.json().get("message", f"未知响应: {res.text[:80]}")
            except Exception:
                message = "系统繁忙" if "频繁" in res.text else f"非JSON: {res.text[:50]}"

            if "选课成功" in message:
                print(f"✅ [{tag}] 抢课成功！")
                return True, None
            else:
                print(f"⏳ [{tag}] {message.strip()}")
                return False, (kc, jx, cno)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if run_mode == 'monitor':
                print(f"⚡ [{tag}] 超时重试 ({attempt+1}/{max_attempts})")
                continue
            else:
                print(f"💥 [{tag}] 网络异常: {e}")
                return False, (kc, jx, cno)
        except Exception as e:
            print(f"💥 [{tag}] 异常: {e}")
            return False, (kc, jx, cno)

    return False, (kc, jx, cno)

# ==============================================================================
#  监控 + 抢课一体化入口
# ==============================================================================
def update_config_id(new_id):
    """将新发现的批次 ID 写入 config.toml 配置文件。"""
    print(f"💾 正在将新批次 ID 写入 config.toml: {new_id}")
    try:
        with open('config.toml', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        with open('config.toml', 'w', encoding='utf-8') as f:
            for line in lines:
                if line.strip().startswith('jx0502zbid') and '=' in line:
                    if not line.strip().startswith('#'):
                        f.write(f"# {line}")
                        f.write(f'jx0502zbid = "{new_id}"\n')
                    else:
                        f.write(line)
                else:
                    f.write(line)
        print("✅ config.toml 已更新。")
        return True
    except Exception as e:
        print(f"❌ 更新 config.toml 失败: {e}")
        return False

def wait_and_monitor(auth_session, known_ids=None):
    """监控 xklc_list 页面，发现新批次 ID 后返回。该页面随时可用，无需等待特定时间。"""
    import re
    if known_ids is None:
        known_ids = []

    # 关键修复：使用 xklc_list 而非 xsxk_index，前者在任何时段都能返回批次信息
    monitor_url = 'https://jwxt.sztu.edu.cn/jsxsd/xsxk/xklc_list'

    if known_ids:
        print(f"ℹ️  已忽略的已知批次 ID: {[kid[:8] + '...' for kid in known_ids]}")
    print("📡 开始监控选课批次列表（xklc_list）...")

    while True:
        try:
            current_time = time.strftime("%H:%M:%S")
            resp = auth_session.get(monitor_url)
            # 同时匹配两种格式：
            # 1. URL参数: jx0502zbid=XXXX
            # 2. JS函数: toxk('XXXX') — xklc_list 页面实际使用的格式
            found_ids = re.findall(r"(?:jx0502zbid=|toxk\(['\"])([A-Fa-f0-9]{32})", resp.text)

            new_id = None
            for fid in found_ids:
                if fid not in known_ids:
                    new_id = fid
                    break

            if new_id:
                print(f"\n{'!' * 50}")
                print(f"🚨 发现新的选课批次 ID: {new_id}")
                print(f"{'!' * 50}")
                return new_id
            else:
                print(f"\r[{current_time}] 暂未发现新批次 ID，10 秒后重试...", end="")

            time.sleep(10)

        except Exception as e:
            print(f"\n❌ 监控出错: {e}，5 秒后重试...")
            time.sleep(5)

def run_course_selection(auth_session):
    """使用已登录的 auth_session 执行抢课循环。"""
    unique_cnos = list(dict.fromkeys([c['cno'] for c in courses_config]))
    for cno_val in unique_cnos:
        auth_session.logintoXK(cno_val)
    start_time = time.time()

    active_groups = {i: c for i, c in enumerate(courses_config)}
    success_count = 0
    round_num = 0

    while active_groups:
        if session_expired:
            raise SessionExpiredError("会话已失效")
            
        sleep_sec = is_in_time_window(schedule_start, schedule_end)
        if sleep_sec > 0:
            h, r = divmod(sleep_sec, 3600)
            m, s = divmod(r, 60)
            print(f"\n🌙 当前时间不在运行时间窗口 ({schedule_start}-{schedule_end})，休眠中...")
            print(f"   距离下次抢课唤醒约有: {int(h)}小时 {int(m)}分钟 {int(s)}秒")
            time.sleep(sleep_sec)
            print("\n☀️ 唤醒时间到，重新激活会话抢课！")
            raise SessionExpiredError("休眠唤醒，需要重新登录以防会话失效")
            
        round_num += 1
        print("\n" + "=" * 50)
        print(f"🔥 第 {round_num} 轮抢课开始！正在抢 {len(active_groups)} 门课程。")
        print(f"   (使用线程池，最大并发数: {max_workers})")
        print("=" * 50)

        tasks = []
        for idx, group in active_groups.items():
            kc = group['kcid']
            cno = group['cno']
            name = group.get('name', '未命名课程')
            for jx in group['jx_list']:
                tasks.append((idx, kc, jx, cno, name))

        round_success_idx = set()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(select_course_worker, auth_session, kc, jx, cno, name): idx
                for (idx, kc, jx, cno, name) in tasks
            }
            for future in future_to_task:
                idx = future_to_task[future]
                if idx in round_success_idx:
                    continue
                
                is_success, failed_course_info = future.result()
                if is_success:
                    round_success_idx.add(idx)

        newly_succeeded = len(round_success_idx)
        if newly_succeeded > 0:
            success_count += newly_succeeded
            def alert_win():
                ctypes.windll.user32.MessageBoxW(0, f"✅ 恭喜！刚刚抢到了 {newly_succeeded} 门课！\n当前总成功数: {success_count}", "抢课成功提醒", 0)
            threading.Thread(target=alert_win, daemon=True).start()
            
            for idx in round_success_idx:
                del active_groups[idx]

        print(f"\n🏁 第 {round_num} 轮结束。本轮抢到 {newly_succeeded} 门课 | 当前总成功数: {success_count} | 剩余课程目标数: {len(active_groups)}")

        if success_count >= target_count:
            print(f"\n🎉【任务达成】已成功抢到 {target_count} 门课程！停止一切脚本。")
            def final_alert_win():
                 ctypes.windll.user32.MessageBoxW(0, f"🎉 已成功抢到 {target_count} 门课程！抢课脚本已自动退出。", "任务达成", 0)
            threading.Thread(target=final_alert_win, daemon=True).start()
            break

        if active_groups:
            if session_expired:
                raise SessionExpiredError("会话已失效")
            wait_time = random.uniform(retry_min, retry_max)
            print(f"🕒 等待 {wait_time:.1f} 秒后开始下一轮...")
            time.sleep(wait_time)

    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"🎉 抢课流程结束！共成功抢到 {success_count} 门课程！")
    print(f"总耗时: {total_time // 60:.0f} 分 {total_time % 60:.2f} 秒")
    print("=" * 60)

if __name__ == "__main__":
    print("🚀 脚本启动，进入无人值守主循环...")
    
    while True:
        try:
            sleep_sec = is_in_time_window(schedule_start, schedule_end)
            if sleep_sec > 0:
                h, r = divmod(sleep_sec, 3600)
                m, s = divmod(r, 60)
                print(f"\n🌙 当前时间不在运行时间窗口 ({schedule_start}-{schedule_end})，休眠中...")
                print(f"   距离下次唤醒约有: {int(h)}小时 {int(m)}分钟 {int(s)}秒")
                time.sleep(sleep_sec)
                print("\n☀️ 唤醒时间到，继续执行！")
            
            session_expired = False
            
            max_login_retries = 180
            auth_session = None
            print("\n🔐 开始验证并登录...")
            for attempt in range(1, max_login_retries + 1):
                try:
                    auth_session = Auth()
                    result = auth_session.login(user, pwd)
                    if result:
                        print("✅ 登录成功！\n")
                        break
                    else:
                        print(f"❌ 登录认证失败（第 {attempt}/{max_login_retries} 次），10 秒后重试...")
                except Exception as login_err:
                    print(f"❌ 登录异常（第 {attempt}/{max_login_retries} 次）: {login_err}")
                
                if attempt == max_login_retries:
                    print("❌ 已达最大重试次数，尝试重置大循环。")
                    break
                    
                time.sleep(10)
                
            if not auth_session or not auth_session.ok:
                time.sleep(5)
                continue

            if run_mode == 'scavenge':
                print("=" * 50)
                print("🔄 捡漏模式：直接进入无限轮询抢课")
                print(f"   批次 ID: {jx0502zbid}")
                print("=" * 50)
                run_course_selection(auth_session)
                
            else:
                print("=" * 50)
                print("📡 首抢模式：高频监控批次 ID")
                print("=" * 50)
                new_id = wait_and_monitor(auth_session)

                if new_id:
                    update_config_id(new_id)
                    globals()['jx0502zbid'] = new_id

                    print("\n" + "=" * 50)
                    print("🎯 成功捕获新批次！即刻爆发抢课！")
                    print("=" * 50)
                    run_course_selection(auth_session)
                else:
                    print("⚠️ 监控未能获取到新的批次 ID，等待重试...")
                    time.sleep(10)

        except SessionExpiredError as se:
            print(f"\n🔄 触发会话重连机制: {str(se)}")
            print("🕒 准备在 5 秒后执行重新登录...")
            time.sleep(5)
            
        except KeyboardInterrupt:
            print("\n🛑 用户手动终止了脚本运行。退出")
            sys.exit(0)
            
        except Exception as e:
            print(f"\n💥 【严重异常】主循环抛出错误: {str(e)}")
            traceback.print_exc()
            print("🛠️ 触发保底恢复机制，10 秒后重启总流程...")
            time.sleep(10)
