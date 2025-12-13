# SpaceFleet - 多服务器磁盘空间管理工具

## 项目概述

一站式管理多个 Linux 服务器磁盘空间的本地 Web 工具。

### 核心功能
- **空间查看**: 实时查看多台服务器的磁盘使用情况
- **趋势分析**: 历史数据记录，可视化展示空间变化趋势
- **用户占用分析**: 统计各用户/目录在数据盘上的空间占用
- **服务器管理**: 统一管理 Ubuntu / CentOS 服务器

### 业务规则
- **磁盘过滤**: 只统计 >= 250GB 的分区，忽略 tmpfs、boot、efi 等系统分区
- **用户分析**: 针对数据盘 (如 /data, /data1) 统计一级子目录的占用情况
- **告警阈值**: 磁盘使用率 >= 80% 时触发告警
- **采集频率**: 每天一次

---

## 技术架构

```
┌─────────────────────────────────────────────────┐
│           Web 前端 (原生 HTML/CSS/JS)            │
│         仪表盘 / 服务器列表 / 趋势图             │
└─────────────────┬───────────────────────────────┘
                  │ HTTP API
┌─────────────────▼───────────────────────────────┐
│              后端 (Python FastAPI)              │
│  - 服务器配置管理                                │
│  - 定时采集任务 (APScheduler)                   │
│  - 数据存储 (SQLite)                            │
└─────────────────┬───────────────────────────────┘
                  │ SSH (paramiko)
┌─────────────────▼───────────────────────────────┐
│           Linux 服务器 (Ubuntu/CentOS)          │
│              执行 df -h, du 等命令               │
└─────────────────────────────────────────────────┘
```

## 技术栈

### 后端
- **框架**: Python + FastAPI
- **SSH 连接**: Paramiko
- **数据库**: SQLite
- **定时任务**: APScheduler

### 前端
- **技术**: 原生 HTML + CSS + JavaScript
- **图表**: Canvas 自绘制
- **无需构建**: 直接由后端提供静态文件服务

---

## 设计决策

### 连接模式: SSH

选择 SSH 模式而非 Agent 模式的原因：

| 方面 | SSH 模式 | Agent 模式 |
|------|----------|------------|
| 服务器端 | 无需安装任何东西 | 需要部署 agent |
| 实现复杂度 | 简单，快速实现 | 稍复杂 |
| 网络要求 | 本地能 SSH 到服务器 | agent 需连接中心服务器 |

> 后续可根据需求扩展为 Agent 模式

---

## 项目结构 (规划)

```
space_manager/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI 入口
│   │   ├── models.py         # 数据库模型
│   │   ├── schemas.py        # Pydantic schemas
│   │   ├── database.py       # 数据库连接
│   │   ├── ssh_client.py     # SSH 连接模块
│   │   └── scheduler.py      # 定时任务
│   └── requirements.txt
├── frontend/
│   ├── index.html            # 主页面
│   ├── css/
│   │   └── style.css         # 样式
│   └── js/
│       ├── api.js            # API 封装
│       ├── chart.js          # 图表模块
│       └── app.js            # 主逻辑
└── README.md
```

---

## 数据模型 (规划)

### Server (服务器配置)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| name | string | 服务器名称 |
| host | string | IP 或域名 |
| port | int | SSH 端口 |
| username | string | SSH 用户名 |
| auth_type | string | 认证方式 (password/key) |
| os_type | string | ubuntu / centos |

### DiskUsage (磁盘使用记录)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| server_id | int | 关联服务器 |
| device | string | 设备名 (/dev/sdb1) |
| filesystem | string | 文件系统类型 (ext4, xfs) |
| mount_point | string | 挂载点 (/, /data 等) |
| total_gb | float | 总容量 |
| used_gb | float | 已使用 |
| free_gb | float | 剩余 |
| use_percent | float | 使用百分比 |
| collected_at | datetime | 采集时间 |

> **过滤规则**: 只采集 total_gb >= 250G 的分区，忽略 tmpfs、boot 等

### UserDiskUsage (用户空间占用)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| server_id | int | 关联服务器 |
| mount_point | string | 所属挂载点 (/data) |
| directory | string | 目录路径 (/data/username) |
| owner | string | 目录所有者 (用户名) |
| used_gb | float | 占用空间 |
| collected_at | datetime | 采集时间 |

> **采集方式**: 对大磁盘的一级子目录执行 `du -s`，统计各用户/项目的占用

---

## 快速启动

### 1. 启动后端 (使用 uv)

```bash
cd backend

# 注意: Python 3.13 兼容性问题，建议使用 Python 3.11/3.12
# 如果当前是 Python 3.13，安装兼容版本:
uv python install 3.12

# 设置清华镜像 (可选，加速下载)
$env:UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"   # Windows PowerShell
# export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple  # Linux/Mac

# 初始化环境并安装依赖 (使用 Python 3.12)
uv sync --python 3.12

# 启动服务
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端 API 文档: http://localhost:8000/docs

### 2. 访问前端

前端已集成到后端服务，无需单独启动。

直接访问: http://localhost:8000

### 3. 使用流程

1. 打开 http://localhost:8000
2. 进入 **服务器管理** 添加要监控的服务器
3. 点击 **测试连接** 验证 SSH 配置
4. （可选）如需避免权限不足导致扫描不全，勾选 **使用 sudo 扫描**，并点击 **测试 sudo**
4. 点击 **采集数据** 或等待每日自动采集
5. 返回 **仪表盘** 查看磁盘概览和趋势

---

## 使用 sudo 扫描（解决权限不足）

当你在服务器管理中勾选 **使用 sudo 扫描** 时，后端会通过 SSH 在远端执行类似命令：

```bash
sudo -n bash -lc "<实际扫描命令>"
```

其中 `-n` 表示 **非交互**：
- 如果需要输入密码，会立刻失败，不会卡住等待输入。

### 现象：sudo 测试失败

如果你看到类似提示：

```
sudo: a password is required
```

说明目标服务器上该 SSH 用户 **没有配置免密 sudo（NOPASSWD）**，或者该用户没有 sudo 权限。

### 解决：配置免密 sudo（推荐用 visudo）

1. 登录到目标服务器（需要具备 sudo 管理权限的账号）
2. 使用 `visudo` 编辑 sudoers（避免语法错误导致 sudo 不可用）：

```bash
sudo visudo
```

3. 追加一条规则（将 `YOUR_USER` 替换为你在 Space Manager 中填写的 SSH 用户名）：

```text
YOUR_USER ALL=(ALL) NOPASSWD: /usr/bin/du, /usr/bin/find, /usr/bin/stat, /bin/df, /bin/bash, /usr/bin/awk, /usr/bin/sort, /usr/bin/head
```

4. 保存退出后，在 Space Manager 中点击 **测试 sudo**，应显示 `✅ 可用`。

### 安全建议

`NOPASSWD` 会提升权限，建议遵循最小授权：
- 只给需要的用户配置
- 尽量只允许必要命令（上面示例已经做了命令白名单）
- 如你的服务器命令路径不同（例如 `du/find` 在 `/bin`），请用 `which du` / `which find` 查到实际路径并替换

---

## 开发计划

- [x] Phase 1: 后端基础框架
- [x] Phase 2: 数据采集 + 定时任务
- [x] Phase 3: 前端界面
- [ ] Phase 4: 增强功能
  - [ ] 告警通知 (邮件/钉钉/企业微信)
  - [ ] 大文件定位
