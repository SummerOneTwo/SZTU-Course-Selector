import base64
import json
import os
import sys
import time
import traceback
import requests
import threading
import random
from configparser import ConfigParser
from Crypto.Cipher import DES
import urllib3
from concurrent.futures import ThreadPoolExecutor

# 禁用InsecureRequestWarning警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 配置加载与校验 ---
try:
    conf = ConfigParser()
    conf.read("config.txt", encoding='utf-8')
    
    # [mysql] section
    user = conf.get('mysql', 'username')
    pwd = conf.get('mysql', 'password')
    cno = conf.get('mysql', 'cno')
    kcid_str = conf.get('mysql', 'kcid')
    jx0404id_str = conf.get('mysql', 'jx0404id')

    # [advanced] section - 新增的可选高级配置
    # 提供默认值，使得旧的配置文件也能兼容
    jx0502zbid = conf.get('advanced', 'jx0502zbid', fallback='248522AF977240AD868F3566F15CDED9')
    max_workers = conf.getint('advanced', 'max_workers', fallback=8)
    round_cool_down_min = conf.getint('advanced', 'round_cool_down_min', fallback=30)
    round_cool_down_max = conf.getint('advanced', 'round_cool_down_max', fallback=90)

    # 将字符串转换为列表，并去除每个ID周围可能存在的空格
    kc_list = [kc.strip() for kc in kcid_str.split(',') if kc.strip()]
    jx_list = [jx.strip() for jx in jx0404id_str.split(',') if jx.strip()]

    # 新增：校验课程ID和教学班ID数量是否匹配
    if len(kc_list) != len(jx_list):
        print("❌ 配置错误: kcid 和 jx0404id 的数量不匹配！请检查 config.txt。")
        print(f"  - kcid 数量: {len(kc_list)}")
        print(f"  - jx0404id 数量: {len(jx_list)}")
        input("按回车键退出...")
        sys.exit(1)

except Exception as e:
    print(f"❌ 读取配置文件 config.txt 失败: {e}")
    print("请确保配置文件存在且格式正确。")
    input("按回车键退出...")
    sys.exit(1)

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
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ' \
                                             'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36'
        self.session.headers['Host'] = 'auth.sztu.edu.cn'
        self.session.headers['Referer'] = 'https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu'
        # ... (其余headers保持不变)
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
        return self.session.get(url, timeout=10, verify=False, allow_redirects=False)

    def post(self, url, data):
        return self.session.post(url, timeout=10, verify=False, data=data, allow_redirects=False)

    def logintoXK(self, cno):
        print("➡️ 正在进入选课系统...")
        # 优化：使用从配置文件读取的选课批次ID
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

# ==============================================================================
#  新的多线程执行逻辑
# ==============================================================================
def select_course_worker(auth_session, kc, jx, cno):
    """
    单个课程的抢课线程工作函数。
    这个函数只执行一次抢课尝试，并返回结果。
    """
    try:
        time.sleep(random.uniform(0.1, 0.5))
        res = auth_session.get_course(kc, jx, cno)
        res_json = res.json()
        message = res_json.get("message", "未知响应")

        if "选课成功" in message:
            print(f"✅ [课程: {kc}] 抢课成功！")
            return True, None # 返回成功状态和空值
        else:
            print(f"⏳ [课程: {kc}] 抢课失败 | 状态: {message.strip()}")
            return False, (kc, jx) # 返回失败状态和课程信息
    except Exception as e:
        print(f"💥 [课程: {kc}] 发生错误: {e}")
        return False, (kc, jx) # 发生错误也视为失败

if __name__ == "__main__":
    try:
        print("🚀 脚本启动，正在执行单次登录...")
        auth_session = Auth()
        if not auth_session.login(user, pwd):
            print("❌ 登录失败，请检查账号密码或网络连接。")
            input("按回车键退出...")
            sys.exit(1)
        print("✅ 登录成功！")
        auth_session.logintoXK(cno)
        start_time = time.time()
        
        remaining_courses = list(zip(kc_list, jx_list))
        success_count = 0
        round_num = 0

        while remaining_courses:
            round_num += 1
            print("\n" + "="*50)
            print(f"🔥 第 {round_num} 轮抢课开始！目标课程数: {len(remaining_courses)}")
            print(f"   (使用线程池，最大并发数: {max_workers})")
            print("="*50)

            round_failures = []
            
            # 优化：使用线程池来控制并发
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交本轮所有任务到线程池
                future_to_course = {executor.submit(select_course_worker, auth_session, kc, jx, cno): (kc, jx) for kc, jx in remaining_courses}
                
                # 获取每个任务的结果
                for future in future_to_course:
                    is_success, failed_course_info = future.result()
                    if not is_success and failed_course_info:
                        round_failures.append(failed_course_info)

            successful_in_round = len(remaining_courses) - len(round_failures)
            success_count += successful_in_round
            remaining_courses = round_failures

            print(f"\n🏁 第 {round_num} 轮结束。本轮成功: {successful_in_round} | 剩余: {len(remaining_courses)}")

            if remaining_courses:
                wait_time = random.uniform(round_cool_down_min, round_cool_down_max)
                print(f"🕒 等待 {wait_time:.1f} 秒后开始下一轮...")
                time.sleep(wait_time)
        
        total_time = time.time() - start_time
        print("\n" + "="*60)
        print(f"🎉 全部完成！成功抢到 {success_count}/{len(kc_list)} 个课程！")
        print(f"总耗时: {total_time//60:.0f} 分 {total_time%60:.2f} 秒")
        print("="*60)
        input("按回车键退出...")

    except Exception as e:
        print(f"\n💥 发生未处理的致命异常: {str(e)}")
        traceback.print_exc()
        input("程序发生异常，按回车键退出...")
