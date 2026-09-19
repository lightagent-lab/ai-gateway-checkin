# AI 中转站自动签到 (ai-gateway-checkin)

一个通用的 AI API 中转站**多账号自动签到**工具。站点地址自己填，程序自动识别站点类型并完成签到。

- **不用改代码**：任何基于 new-api / sub2api 家族的站点，填上地址就能用
- **图形界面**：双击 exe，填站点和账号，点「一键签到」
- **多账号多站点**：一个界面管理所有账号，支持并发
- **自动识别**：自动判断站点是哪个家族、走哪套登录和签到接口

## 快速开始

### 方式一：下载 exe（推荐）

1. 到 [Releases](https://github.com/lightagent-lab/ai-gateway-checkin/releases/latest) 下载 `ai-gateway-checkin.exe`
2. 双击运行
3. 点「＋ 添加账号」，填站点地址 + 账号密码
4. 点「一键签到」

首次添加账号前，建议先在「默认站点」里填好地址，点「检测站点」确认能正常识别。

### 方式二：源码运行

```bash
git clone <repo>
cd ai-gateway-checkin
pip install -r requirements.txt
python gui_app.py          # 图形界面
```

### 命令行用法

```bash
python cli.py detect https://example.com    # 检测站点类型
python cli.py check                          # 全部账号签到
python cli.py status                         # 只看状态
python cli.py loop --at 08:30                # 常驻定时签到
python cli.py -a accounts.txt -w 5 check     # 指定文件和并发
```

## 支持的站点

程序会自动识别两类家族：

| 家族 | 识别特征 | 登录接口 | 签到接口 |
|---|---|---|---|
| **new-api** | `/api/status` 返回 `version`/`system_name` | `POST /api/user/login` | `GET/POST /api/user/checkin` |
| **sub2api** | 页面内嵌 `window.__APP_CONFIG__` | `POST /api/v1/auth/login` | 自动探测（见下） |

对 new-api 家族，签到路径是固定的。
对 sub2api 家族，因为**上游主干本身没有签到功能**（签到是各站点自行二开添加的），
程序会依次探测多个候选路径，并用响应结构判断是否命中：

```
/user/checkin, /user/check-in, /user/daily-checkin, /checkin,
/user/sign-in, /user/signin, /user/daily, /user/reward/checkin
```

如果某个站点用的是别的路径，找到后告诉我，或自己加到 `uc/client.py` 的
`SUB2API_CHECKIN_CANDIDATES` 里即可。

## 账号文件格式

```
# 格式：站点 用户名 密码 [备注] [代理]
https://example.com  user@mail.com  mypassword  小号A
https://other.com    user2           pass2       小号B  http://127.0.0.1:7890
```

也支持逗号、竖线或 `----` 分隔。站点可以省略，用界面里的「默认站点」补齐。

## 功能

- 自动识别站点类型，不用手动选
- token 缓存复用，不重复登录；失效自动刷新
- 每账号独立设备指纹，多号不互相牵连
- 重复签到自动识别，不会重复请求
- 区分「成功 / 已签到 / 失败 / 站点不支持签到」
- 并发可调，失败自动重试退避
- 支持每个账号挂独立代理
- 结果可导出 CSV
- 每天定时自动签到

## 打包

```bash
pip install pyinstaller
python build_exe.py
# 产物：dist/ai-gateway-checkin.exe
```

## 自检与排障

打包后或运行异常时，可以用自检模式确认环境：

```bash
ai-gateway-checkin.exe --selftest                    # 检查依赖 + 网络 + 识别默认站点
ai-gateway-checkin.exe --detect https://example.com  # 检测指定站点
ai-gateway-checkin.exe --version                     # 显示版本
```

自检结果也会写入同目录的 `selftest.log`。

## 项目结构

```
ai-gateway-checkin/
├── gui_app.py            # 图形界面入口
├── cli.py                # 命令行入口
├── uc/
│   ├── sites.py          # 站点家族识别 + 请求会话
│   ├── client.py         # 登录/状态/签到 + 端点探测
│   ├── runner.py         # 批量执行引擎
│   ├── store.py          # 账号模型 + token 缓存
│   ├── crypto_util.py    # new-api RSA 密码加密登录
│   ├── fonts.py          # 字体加载与选择
│   └── selftest.py       # 自检
├── tests/
│   ├── mock_site.py      # 模拟两类家族的测试服务器
│   ├── test_e2e.py       # 端到端测试
│   ├── test_gui.py       # 界面功能测试
│   └── test_layout.py    # 布局回归测试
├── assets/               # 字体存放目录（不入库）
├── build.spec            # PyInstaller 配置
├── build_exe.py          # 一键打包脚本
└── requirements.txt
```

## 关于代理

- 站点填本机或内网地址时，程序会强制直连，忽略系统代理
  （否则挂了 Clash 之类的全局代理会被转发导致失败）
- 填公网站点时，尊重系统代理设置
- 想给某个账号单独指定代理，在账号的「代理」栏填即可

## 测试

```bash
# 终端 1：启动模拟站点
python tests/mock_site.py 8901 new-api
python tests/mock_site.py 8902 sub2api

# 终端 2：跑测试
python tests/test_e2e.py     # 29 项端到端检查
python tests/test_gui.py     # 12 项界面检查
python tests/test_layout.py  # 18 项布局检查
```

## 字体

界面默认使用 **苹方（PingFang SC）**，找不到时自动回退到系统字体，不影响使用。

查找顺序：

1. `assets/PingFangSC-Semibold.otf`（程序同目录）
2. 打包进 exe 的字体资源
3. 常见下载目录（如 `~/Downloads/Telegram Desktop/`）
4. 系统已安装的同类字体（微软雅黑 → 思源黑体 → 黑体 → 宋体）

想自定义字体，把 OTF/TTF 放到程序同目录的 `assets/` 下并命名为
`PingFangSC-Semibold.otf` 即可。程序会用 `AddFontResourceEx(FR_PRIVATE)`
私有加载，不会影响系统字体设置。

> **注意**：苹方是 Apple 的专有字体，本仓库**不包含**该字体文件。
> 请自行确认你有权使用，且不要把含该字体的构建产物公开分发。

## 关于界面尺寸

界面按屏幕分辨率自适应（宽度取屏幕 72%，高度 76%），并有最小尺寸保护。
所有主要按钮都保证有足够空间，不会出现按钮被挤没的情况。

`tests/test_layout.py` 会在真实窗口中测量每个控件的实际尺寸，
确保没有 1×1 的不可点击控件、没有超出窗口的区域。

## 免责声明

本项目仅供学习与个人自动化使用。请遵守你所用站点的服务条款，
不要用于批量注册、薅羊毛等违反站点规则的行为。
因使用本工具产生的任何后果由使用者自行承担。

## License

MIT