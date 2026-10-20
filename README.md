# ChatBot

基于 **LangGraph 和千问模型** 的聊天机器人。提供适配电脑与手机的独立网页界面，支持访问密码、流式回复、多轮聊天和 SQLite 历史记录保存。也可以使用 LangSmith Studio 调试图和会话。

默认使用 `qwen3.7-flash`，模型名称和 API 地址均可通过环境变量调整。默认人设位于 [`prompts.py`](./prompts.py)，可以根据自己的需求修改。

## 环境要求

- 推荐 Python **3.12**；本地 Agent Server 要求 Python **3.11 或以上**。
- Miniconda 或 Anaconda，推荐创建名为 `agent` 的环境。
- 千问平台 API Key，以及该 Key 有权限调用的模型和对应 API 地址。
- 独立网页模式只需要千问 API Key 和自己设置的访问密码，不依赖 Studio 或 LangSmith 账号。
- 使用可选的 Studio 调试模式时，按照官方流程准备 LangSmith 账号和 API Key。

Windows 提供双击启动脚本；其他系统可以使用下文的命令行启动方式。当前版本在 Windows / Python 3.12 环境中验证。

## 快速开始

### 1. 获取项目

克隆本仓库后，在终端进入包含 `langgraph.json` 的项目根目录。

### 2. 创建环境并安装依赖

在 Anaconda Prompt 或能够使用 Conda 的终端中运行：

```powershell
conda create -n agent python=3.12 pip -y
conda activate agent
python -m pip install -r requirements.txt
```

`requirements.txt` 同时包含模型适配包和本地开发服务器，无需另外安装 LangGraph CLI。文件固定了已验证的核心版本，但不是全部间接依赖的完整锁文件。

### 3. 配置 API Key

在项目根目录复制配置示例：

```powershell
Copy-Item .env.example .env
```

编辑新创建的 `.env`，填写自己的配置：

```dotenv
QWEN_API_KEY=你的千问_API_Key
QWEN_MODEL=qwen3.7-flash
QWEN_BASE_URL=https://maas.qianwenaiapi.com/compatible-mode/v1

LANGSMITH_API_KEY=你的LangSmith_API_Key
LANGSMITH_TRACING=false

# 网页访问密码，至少 8 个字符；不要使用模型 API Key 作为密码。
CHAT_PASSWORD=你自己设置的访问密码
CHAT_DATA_DIR=data/web
CHAT_COOKIE_SECURE=false
```

`QWEN_BASE_URL` 必须与申请 Key 的平台、地域和接口类型匹配。示例使用千问 AI 平台的 OpenAI 兼容接口；使用阿里云百炼等其他入口时，请以相应控制台显示的地址为准，不能只复制一个与 Key 不匹配的地址。

| 配置项 | 作用 |
| --- | --- |
| `QWEN_API_KEY` | 调用千问模型，必填 |
| `QWEN_MODEL` | 模型标识，默认 `qwen3.7-flash`；需要有相应调用权限 |
| `QWEN_BASE_URL` | OpenAI 兼容接口地址，填写到 `/v1`，不要再追加 `/chat/completions` |
| `LANGSMITH_API_KEY` | 仅在使用 Studio 或 LangSmith 追踪时配置 |
| `CHAT_PASSWORD` | 独立网页的访问密码，至少 8 个字符 |
| `CHAT_DATA_DIR` | 网页会话和检查点的保存目录，默认 `data/web` |
| `CHAT_COOKIE_SECURE` | 本地 HTTP 使用 `false`，以后配置 HTTPS 时使用 `true` |
| `LANGSMITH_TRACING` | `true` 将调用轨迹及消息记录到 LangSmith；`false` 关闭该追踪 |

模型调用本身仍会将消息发送给所配置的模型服务。已有系统环境变量优先于 `.env` 中的同名值；如果修改 `.env` 后没有变化，请检查终端是否设置了同名变量，并重启服务。

`.env` 已被 Git 忽略。仓库中只发布不含真实密钥的 `.env.example`。

### 4. 启动独立网页（推荐）

完成依赖安装，并在 `.env` 中填写 `QWEN_API_KEY` 和 `CHAT_PASSWORD` 后，双击 **`start_web.bat`**，或在 PowerShell 中运行：

```powershell
.\start_web.bat
```

浏览器会自动打开 <http://127.0.0.1:8000>。输入自己设置的访问密码，即可使用独立聊天页面。

- 左侧新建、切换或删除对话；电脑端可用侧栏顶部图标收起或展开侧边栏，收起状态会在当前浏览器中保留。消息区域独立滚动，长对话不会挤走底部输入框，向上浏览时可点击「回到最新」。
- 每次发送一条新消息，机器人边生成边回复；生成期间可点击停止按钮。
- 记录保存到 SQLite，关闭或重启网页服务后可以继续原会话。
- 左下角齿轮图标展开伙伴昵称、界面配色、聊天背景和退出登录。侧栏收起后仍能使用齿轮设置和新建对话，保存设置后刷新或重启仍然保留。
- 浏览器只与自己的 Python 后端通信，模型 API Key 不会发给网页。
- 这是单个访问密码的私人聊天应用，所有通过该密码登录的设备共享会话列表，不是多用户账户系统。

也可以在激活 `agent` 的终端中手动启动：

```powershell
python run_web.py
```

macOS / Linux 同样可以运行 `python run_web.py --no-browser`；Windows 启动脚本自动设置 UTF-8。默认仅监听本机 `127.0.0.1`，不开放到公网。

**在同一 Wi-Fi 下用手机访问：**

```powershell
.\start_web.bat --host 0.0.0.0
```

然后在手机浏览器输入 `http://电脑的局域网IP:8000`。电脑和手机需要能够互相访问；Windows 防火墙如有提示，应仅允许需要的专用网络。这种方式仍需要电脑保持运行；以后部署到自己的服务器并配置 HTTPS 后，才能在外网随时访问。

**个性化设置：**

- **伙伴昵称**：统一显示在侧边栏、消息署名和浏览器标题，也会在下一次模型调用时加入系统提示词，保留原有人设。支持 1～24 个字符；不再提供独立的应用名称设置，旧版保存的昵称、配色、背景和聊天记录会继续保留。
- **三种配色**：雨雾紫、樱花粉、晴空蓝，沿用柔和的浅色风格。展开侧边栏后的会话标题与主要按钮为 18px，日期和辅助文字为 15～16px，聊天正文保持 16px。
- **聊天背景**：支持有效的 PNG / JPG / JPEG 图片，最大 8 MB、2000 万像素，单边不超过 10000px。图片保持比例并居中铺满聊天区域，随屏幕大小适配，边缘可能裁切；可调整显示强度或移除背景。
- 设置窗口会即时预览，点击「保存设置」后生效；取消或关闭窗口会恢复原设置。设置与背景保存在后端 SQLite 中，同一服务下的其他设备刷新后也会使用这些设置。

`CHAT_DATA_DIR` 下的 `conversations.sqlite` 保存会话索引、个性化设置和上传的背景图片，`checkpoints.sqlite` 保存 LangGraph 消息状态，`session.key` 用于保护登录 Cookie。备份或迁移时，在停止服务后备份整个目录；不要提交它，也不要把数据目录作为静态文件目录。已有版本启动时会自动增加设置表，保留原来的聊天记录。

网页服务目前按单进程运行，启动器使用一个 worker；多进程或多用户部署需要另行设计会话锁和存储。当前没有执行公网部署。原 Notebook 和 Studio 的历史不会自动导入网页版。

### 5. 可选：使用 Studio 调试

**Windows 双击启动：**

在资源管理器中双击 `start_chatbot.bat`，也可以在 PowerShell 中运行：

```powershell
.\start_chatbot.bat
```

脚本会切换到自身所在的项目目录，查找 `agent` 环境，启用 Python UTF-8 模式，检查基础配置和依赖，再启动服务并自动打开 Studio。UTF-8 设置只影响启动器及其子进程，无需修改第三方包或系统全局配置。

如果 Conda 安装在自定义位置而脚本没有找到环境，可以从 Anaconda Prompt 激活 `agent` 后运行脚本；也可以在已激活环境的 PowerShell 中指定当前环境路径：

```powershell
$env:AGENT_ENV = $env:CONDA_PREFIX
.\start_chatbot.bat
```

两个启动脚本都不会自动创建环境或安装依赖；首次使用时请先完成前面的安装步骤。Windows `.lnk` 快捷方式绑定本机路径，不随仓库发布。如有需要，请在自己的电脑上为脚本创建桌面快捷方式。

**手动启动：**

```powershell
conda activate agent
$env:PYTHONUTF8 = "1"
python -m langgraph_cli dev
```

macOS / Linux 在已激活的环境中可以使用：

```bash
PYTHONUTF8=1 python -m langgraph_cli dev
```

服务默认地址：

- API：<http://127.0.0.1:2024>
- API 文档：<http://127.0.0.1:2024/docs>
- [Studio 聊天与调试界面](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024)

聊天时保持服务窗口运行。停止服务时在窗口按 `Ctrl+C`。

如果端口被占用，可以指定其他端口：

```powershell
.\start_chatbot.bat --port 2025
```

使用终端此次实际输出的 Studio 链接，不要继续连接旧端口。

## 在 Studio 中聊天和调试

1. 打开服务输出的 Studio 链接，登录并选择 `chatbot` 图。
2. 在 **Chat 模式**中发送消息，机器人会逐轮回复。
3. 在同一个 Thread 中继续输入，服务会恢复该会话的消息状态。
4. 新建 Thread 可以开始独立会话；切回旧 Thread 可以查看并继续原会话。
5. 在 **Graph 模式**查看 `chatbot` 节点和 `messages` 状态。若需要查看实际模型输入中的系统提示词，可开启 LangSmith tracing，再检查模型调用轨迹。

可用“先告诉机器人一个暗号，再询问暗号”的方式检查上下文是否生效，并在新 Thread 中确认会话相互隔离。

## 代码与会话保存

```text
ChatBot/
├── chatbot.py          # 状态、模型、chatbot 节点与导出的 graph
├── prompts.py          # 默认系统提示词
├── langgraph.json      # 图入口、项目依赖和环境变量配置
├── requirements.txt    # 应用与本地开发服务依赖
├── start_web.bat       # 独立网页启动入口
├── run_web.py          # 网页服务启动参数与自动打开浏览器
├── webapp.py           # 登录、会话 API、流式回复和 SQLite 保存
├── personalization.py  # 名称、主题与背景图片的校验和持久化
├── web/                # 本地 HTML、CSS、JavaScript 与图标
├── scripts/            # 两个启动器共用的环境查找逻辑
├── tests/              # 使用模拟模型的网页集成测试
├── start_chatbot.bat   # 可选的 Studio 服务启动入口
├── .env.example        # 可公开的配置模板
├── .gitattributes      # Git 文本与脚本换行规则
├── .gitignore          # 密钥、会话、Notebook 等忽略规则
└── README.md
```

`chatbot.py` 每次将“系统人设 + 当前会话消息”交给模型，节点只返回新增的助手回复，由 `add_messages` 合并消息。

Studio 模式通过 `graph_builder.compile()` 导出图；接入 Agent Server 后，检查点和 Thread 由服务管理。独立网页模式则复用同一份模型和人设，使用异步节点与 `AsyncSqliteSaver` 自行持久化会话。Notebook 中手动连接 SQLite 的代码不参与 Studio 应用，已有 Notebook 数据也不会自动迁移到 Studio。

本地服务产生的 `.langgraph_api/`、Notebook 产生的 `data/` 和数据库文件均属于本机运行数据，已被忽略。`langgraph dev` 是开发测试服务，不应将这些开发数据作为生产环境的数据保障；正式部署应配置相应的持久化基础设施。

学习用的 `init.ipynb` 保留在作者本地，不包含在 GitHub 仓库中，启动应用不依赖它。

## 运行网页测试

```powershell
python -m unittest discover -s tests -v
```

测试使用模拟模型和临时数据库，不调用真实千问 API。覆盖登录与 Cookie、流式消息、多轮上下文、会话隔离、重启恢复、删除、输入校验、错误处理，以及个性化设置、背景上传、昵称提示词和前端资源版本更新。

## 常见问题

| 问题 | 检查方式 |
| --- | --- |
| 网页提示没有设置访问密码 | 在 `.env` 中设置至少 8 个字符的 `CHAT_PASSWORD`，然后重启网页服务 |
| 网页登录后手机看不到原来的聊天 | 确认访问的是同一个网页服务实例、同一个数据目录；Studio 与独立网页不共享历史 |
| 更新后布局还是旧的、设置没有反应 | 先关闭旧服务并重新启动，再按 `Ctrl+F5` 刷新；页面会使用带版本的脚本和样式，避免继续复用旧缓存 |
| 找不到 `agent` 环境 | 先创建环境；自定义安装位置可以激活环境后启动，或设置 `AGENT_ENV` |
| 找不到 LangGraph CLI 或其他依赖 | 激活正确环境后重新运行 `python -m pip install -r requirements.txt` |
| 提示缺少 `.env` 或 `QWEN_API_KEY` | 从 `.env.example` 创建 `.env` 并填写自己的 Key |
| `gbk` / `UnicodeDecodeError` | 使用项目启动脚本；手动启动时先设置 `PYTHONUTF8=1` |
| 401、403 或找不到模型 | 核对 Key、模型权限及 `QWEN_BASE_URL` 是否属于同一平台和地域 |
| Studio 无法连接 | 保持本地服务运行，并使用本次启动输出的地址；必要时允许浏览器访问本地服务 |
| 修改人设后看起来没有变化 | 检查模型输入中是否包含系统提示词，尝试新 Thread，确认运行的是当前项目 |

## 参考文档

- [LangGraph 本地服务](https://docs.langchain.com/oss/python/langgraph/local-server)
- [LangGraph 应用结构](https://docs.langchain.com/oss/python/langgraph/application-structure)
- [Studio 的聊天、图和会话操作](https://docs.langchain.com/langsmith/use-studio)
- [LangGraph 持久化机制](https://docs.langchain.com/oss/python/langgraph/persistence)
- [千问模型接入 LangChain](https://help.aliyun.com/zh/model-studio/use-bailian-in-langchain)
