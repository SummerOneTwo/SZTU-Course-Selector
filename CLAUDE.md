# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SZTU-Course-Selector 是深圳技术大学教务系统自动化选课工具。支持自动登录、批次监控、多线程抢课和时间窗口控制。

**注意**: 智能冲突检测和方案生成功能已分离到 [SZTU-Course-Agent](../SZTU-Course-Agent/) 仓库。

## Common Commands

```bash
# 使用 run.bat 一键启动（Windows）
run.bat

# 或使用 uv 运行
uv run sztu_course_selector.py

# 运行爬虫获取课程数据
uv run crawler.py
```

## Project Structure

```
SZTU-Course-Selector/
├── crawler.py                       # 课程数据爬虫
├── debug_selenium.py               # Selenium 调试工具
├── playwright_capture.py            # Playwright 网络捕获工具
├── run.bat                        # Windows 一键启动脚本
├── config.toml                    # 用户配置（不纳入版本控制）
├── config.toml.example            # 配置模板
├── pyproject.toml                 # 项目配置
└── CLAUDE.md                     # 本文件
```

## Configuration Format

`config.toml` 配置文件结构：

```toml
[account]
username = "学号"
password = "密码"

[[courses]]
name = "课程显示名称"
kcid = "课程ID"
cno = "0"              # "0"=必选计划, "1"=跨年级
jx0404id = ["教学班ID1", "教学班ID2"]  # 尝试每个直到成功

[settings]
mode = "scavenge"      # "monitor"=首抢, "scavenge"=捡漏
target_count = 1       # 抢到多少个课程组后停止
jx0502zbid = "XXXX"    # 批次ID（捡漏模式必填）
max_workers = 8         # 线程池大小
schedule_start = "08:55"  # 选课时间窗口
schedule_end = "22:00"
```

## Running Modes

### 首抢模式 (`mode = "monitor"`)
```
启动 → 登录 → 等待指定时间 → 监控批次ID → 发现新批次 → 立即抢课
```
用于：选课系统未开放，需要第一时间抢课

### 捡漏模式 (`mode = "scavenge"`)
```
启动 → 登录 → 使用已有批次ID → 无限轮询抢课
```
用于：选课系统已开放，课程已满，等待别人退课后捡漏

## Key Components

### Auth 类 (sztu_course_selector.py)
- `login()`: 处理教务系统登录（包含 DES 加密）
- `logintoXK()`: 进入选课系统
- `get_course()`: 提交选课请求

### 主流程 (sztu_course_selector.py)
- `wait_and_monitor()`: 监控 `xklc_list` 页面获取新批次ID
- `run_course_selection()`: 多线程并发抢课主循环
- `select_course_worker()`: 单课程选课工作函数

### 时间窗口控制
- `is_in_time_window()`: 检查当前是否在选课时间窗口内
- 窗口外时自动休眠到下次窗口开始时间

## Crawler (crawler.py)

爬取课程数据的功能：
- 支持 5 种选课类型：本学期计划选课、跨年级、公选课、实验、跨专业
- 自动获取所有批次ID
- 输出 JSON 格式课程数据（包含 `_course_type` 字段）
- 支持遍历字符查询（跨年级/跨专业选课）

## Dependencies

- `playwright`: 浏览器自动化（爬虫使用）
- `selenium`: 浏览器自动化（调试工具使用）
- `pycryptodome`: DES 加密（登录密码）
- `requests`: HTTP 请求
- `urllib3`: 连接池和重试策略
- `tomli`: TOML 配置文件读取

## Course Data Format

爬虫输出的 JSON 格式：

```json
{
  "kcmc": "课程名称",
  "kcid": "课程ID",
  "jx0404id": "教学班ID",
  "skls": "教师",
  "skdd": "教室",
  "sksj": "1-16周 星期一 8-10",
  "xkrs": 30,
  "pkrs": 50,
  "xf": 4.0,
  "_course_type": "本学期计划选课"
}
```

## 网络请求关键端点

- `https://auth.sztu.edu.cn/...`: 统一认证登录
- `https://jwxt.sztu.edu.cn/jsxsd/xsxk/xklc_list`: 批次列表（用于监控）
- `https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/bxqjhxkOper`: 选课请求（本学期）
- `https://jwxt.sztu.edu.cn/jsxsd/xsxkkc/knjxkOper`: 选课请求（跨年级）
