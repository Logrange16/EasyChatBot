# QuestMate

| **QuestMate — A dual-mode agent for autonomous research and personalized companionship.**

基于 LangGraph 和千问模型的聊天网站，提供陪伴模式和助手模式，支持电脑与手机浏览器、访问密码、流式回复和 SQLite 历史记录。

- **陪伴模式**：使用通用聊天人设，可在网页中自定义伙伴昵称、性格和交流方式，也支持服务器本地人设文件。
- **助手模式**：主题分析 → 自主检索 → 摘要 → 反思 → 最终摘要。模型通过工具调用决定是否检索以及何时完成，不强制每轮联网。
- **消息排版**：支持 Markdown 和 LaTeX 数学公式，渲染库与字体随项目提供，无需安装 LaTeX。
- **可选 Studio 调试**：两种模式导出独立的 LangGraph 图。

这是单个访问密码的个人应用，所有登录设备共享会话和设置，不是多用户账户系统。

## 安装

推荐 Python **3.12**，当前依赖在 Windows / Python 3.12 中验证。Linux 和 macOS 可以通过命令行启动；Linux 部署仍需在目标服务器验证。

在项目根目录创建虚拟环境并安装依赖：

```bash
python3.12 -m venv .venv
```

Linux / macOS：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

也可以使用 Conda 创建 Python 3.12 的 `agent` 环境。Windows 双击启动脚本默认查找该环境；使用 `.venv` 时可直接执行 `python run_web.py`。

## 配置

在 `.env` 中填写自己的配置：

| 配置项 | 用途 |
| --- | --- |
| `QWEN_API_KEY` | 模型服务密钥，必填 |
| `QWEN_MODEL` | 模型标识，默认 `qwen3.7-flash`，须有调用权限 |
| `QWEN_BASE_URL` | 与密钥所属平台一致的 OpenAI 兼容接口地址，填写到 `/v1` |
| `CHAT_PASSWORD` | 网站访问密码，至少8个字符 |
| `TAVILY_API_KEY` | 可选；填写后启用两种模式的网页检索 |
| `CHAT_DATA_DIR` | 会话和设置目录，默认 `data/web` |
| `CHAT_COOKIE_SECURE` | 本地 HTTP 为 `false`，公网 HTTPS 为 `true` |
| `COMPANION_PROMPT_FILE` | 可选的私有人设文件路径，相对路径以项目根目录为准 |
| `LANGSMITH_API_KEY` | 可选 Studio 调试配置 |
| `LANGSMITH_TRACING` | 默认 `false`；开启后调用轨迹及消息可能发送到 LangSmith |

模型调用会将消息和系统提示词发送到配置的模型服务，网页检索会将查询发送给 Tavily。已有系统环境变量优先于 `.env`；修改服务环境后应重启。

## 启动网页

```bash
python run_web.py --no-browser
```

访问 `http://127.0.0.1:8000` 并输入访问密码。Windows 也可以双击 `start_web.bat`，前提是已创建并安装好 `agent` 环境。

同一局域网的手机访问：

```bash
python run_web.py --host 0.0.0.0 --port 8000 --no-browser
```

在手机浏览器访问电脑的局域网地址。公网部署应配置 HTTPS、反向代理和进程守护，后端仅监听本机。服务按单进程运行，不能直接增加 worker 数量。

## 自定义陪伴人设

网页左下角设置 → **伙伴与人设**，填写昵称和人设并保存；下一次陪伴模式回复生效，助手模式保持独立。人设保存在服务器本地 SQLite 中，不写入源码。

也可以创建 UTF-8 文件 `data/companion_prompt.md`，或通过 `COMPANION_PROMPT_FILE` 指定其他文件。人设选择顺序为：

1. 网页已保存的非空人设，或 Studio 调用配置中的 `configurable.companion_prompt`。
2. 服务器本地人设文件。
3. 源码中不含私人设定的通用默认人设。

网页人设留空会恢复服务器默认设置；本地文件不会自动回传到网页设置框。人设最多20000字符。把自定义文件放在已忽略的 `data/` 下，避免误提交。使用其他路径时，需要自行添加对应的忽略规则。

## Studio 调试

配置好 `.env` 和 LangSmith 后运行：

```bash
python -m langgraph_cli dev
```

Windows 可用 `start_chatbot.bat`。手动启动遇到编码问题时设置 `PYTHONUTF8=1`。选择 `chatbot`（陪伴）或 `assistant`（助手）图；Studio 与独立网页分别管理会话，不共享历史。Studio 默认读取本地人设文件。

## 代码结构

```text
chatbot_app/
├── companion/        # 陪伴模式的 graph、TypedDict State、人设加载
├── assistant/        # 主题、检索、摘要、反思与最终发布
├── shared/           # 模型配置、工具、公共状态和路径
└── web/              # 网站后端、启动器、个性化设置及静态资源
scripts/              # Windows 启动器共用的环境定位逻辑
run_web.py            # 独立网页入口
langgraph.json        # Studio 图入口
requirements.txt      # 固定已验证的核心依赖版本
.env.example          # 不含真实密钥的配置模板
```

依赖方向为 `web → companion / assistant → shared`。助手在内部 `research_messages` 中开展研究，只将反思完成后的摘要写入公开 `messages`。研究和反思通过 `tools_condition` 判断工具调用；执行上限只用于中止失控循环，不会把草稿当成最终摘要。

## 数据与发布

`.env`、`data/`、`.langgraph_api/`、Notebook、`docs/`、`tests/`、缓存和本地调试产物不随仓库发布。应用不依赖本地文档、测试或 Notebook 启动。

`CHAT_DATA_DIR` 下包含会话数据库、检查点、个性化设置、背景图及登录 Cookie 签名密钥。备份时先停止服务，再备份整个目录；不要将它作为静态目录对外提供。

`.gitignore` 只阻止未跟踪文件加入后续提交，无法清除已有提交中的隐私。公开已有仓库前，还应检查 Git 历史与提交作者信息。人设文件不随仓库发布，也不代表模型服务或拥有网站登录权限的人无法接触相关内容。

第三方渲染库许可证保存在 `chatbot_app/web/static/vendor/` 中，发布时需要保留。

## 界面预览

![alt text](images/UI_Preview.png)
