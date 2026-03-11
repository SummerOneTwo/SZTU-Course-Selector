# 技术文档

## 架构概览

```
sztu_course_selector.py
├── Auth 类
│   ├── login()              完整 SSO 登录流程
│   ├── logintoXK()          进入选课系统
│   ├── get_course()         提交单次选课请求
│   ├── checkencryptByDES()     DES 密码加密
│   ├── get() / post()       HTTP 请求封装
│   └── check_login()        校验登录状态
├── select_course_worker()   单课程抢课线程函数
├── update_config_id()       更新批次 ID 到配置文件
├── wait_and_monitor()       监控批次 ID（首发模式）
├── run_course_selection()   多线程抢课主循环
└── is_in_time_window()     时间窗口检查
```

## 认证与登录

### SSO 登录流程

教务系统使用深圳技术大学统一身份认证（SZTU IdP）：

1. GET `https://jwxt.sztu.edu.cn/` → 302 重定向
2. 跟随重定向链（3跳）到认证页
3. POST `ActionAuthChain` 提交学号 + DES 加密密码
4. POST `AuthnEngine` 完成 SAML 认证
5. GET 落地 URL 获取最终 JSESSIONID

### 密码加密

使用 **DES-ECB** 模式 + PKCS5 Padding，密钥为 `PassB01Il71`（前 8 字节）

### Cookie 结构

登录后 Session 包含：`JSESSIONID={old};JSESSIONID={new};SERVERID={server}`

## 选课逻辑

### 课程分组（Target Count 模式）

- 每一门课（`kcid` 相同）作为一个分组
- 同一分组内可配置多个 `jx0404id`（不同老师/时间段）
- 抢到分组内任意一个 `jx0404id` 即视为该课程成功
- 停机条件：`target_count` - 抢到的课程组数量

### 选课请求

```python
# 必修计划 (cno=0)
GET /jsxsd/xsxkkc/bxqjhxkOper?kcid={kcid}&cfbs=null&jx0404id={jxid}&xkzy=&trjf=

# 跨年级 (cno=1)
GET /jsxsd/xsxkkc/knjxkOper?kcid={kcid}&cfbs=null&jx0404id={jxid}&xkzy=&trjf=
```

响应 JSON 的 `message` 字段包含 `"选课成功"` 表示成功。

## 批次监控（首发模式）

监控 `https://jwxt.sztu.edu.cn/jsxsd/xsxk/xklc_list` 页面：

- 正则匹配：`r"(?:jx0502zbid=|toxk\(['\"])([A-Fa-f0-9]{32})"`
- 过滤已知的旧批次 ID
- 发现新 ID → 立即返回并写入配置

## 时间窗口控制

- 检查当前时间是否在 `schedule_start` 到 `schedule_end` 之间
- 窗口外时：计算距离下次窗口开始的秒数并休眠
- 窗口内时：正常执行抢课轮询
