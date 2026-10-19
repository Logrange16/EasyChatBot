# ChatBot

基于 **LangGraph、千问模型和 LangSmith Studio** 的聊天机器人学习项目。支持自定义人设、流式回复、同一会话中的多轮对话，以及在 Studio 中查看消息状态和调试执行过程。

默认使用 `qwen3.7-flash`，模型名称和 API 地址均可通过环境变量调整。默认人设位于 [`prompts.py`](./prompts.py)，可以根据自己的需求修改。

## 环境要求

- 推荐 Python **3.12**；本地 Agent Server 要求 Python **3.11 或以上**。
- Miniconda 或 Anaconda，推荐创建名为 `agent` 的环境。
- 千问平台 API Key，以及该 Key 有权限调用的模型和对应 API 地址。
- 使用 Studio 时，按照官方流程准备 LangSmith 账号和 API Key。

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
```

`QWEN_BASE_URL` 必须与申请 Key 的平台、地域和接口类型匹配。示例使用千问 AI 平台的 OpenAI 兼容接口；使用阿里云百炼等其他入口时，请以相应控制台显示的地址为准，不能只复制一个与 Key 不匹配的地址。

| 配置项 | 作用 |
| --- | --- |
| `QWEN_API_KEY` | 调用千问模型，必填 |
| `QWEN_MODEL` | 模型标识，默认 `qwen3.7-flash`；需要有相应调用权限 |
| `QWEN_BASE_URL` | OpenAI 兼容接口地址，填写到 `/v1`，不要再追加 `/chat/completions` |
| `LANGSMITH_API_KEY` | 按 Studio 官方接入流程配置 |
| `LANGSMITH_TRACING` | `true` 将调用轨迹及消息记录到 LangSmith；`false` 关闭该追踪 |

模型调用本身仍会将消息发送给所配置的模型服务。已有系统环境变量优先于 `.env` 中的同名值；如果修改 `.env` 后没有变化，请检查终端是否设置了同名变量，并重启服务。

`.env` 已被 Git 忽略。仓库中只发布不含真实密钥的 `.env.example`。

### 4. 启动服务

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

启动脚本不会自动创建环境或安装依赖；首次使用时请先完成前面的安装步骤。Windows `.lnk` 快捷方式绑定本机路径，不随仓库发布。如有需要，请在自己的电脑上为脚本创建桌面快捷方式。

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
├── start_chatbot.bat   # Windows 双击启动入口
├── .env.example        # 可公开的配置模板
├── .gitattributes      # Git 文本与脚本换行规则
├── .gitignore          # 密钥、会话、Notebook 等忽略规则
└── README.md
```

`chatbot.py` 每次将“系统人设 + 当前会话消息”交给模型，节点只返回新增的助手回复，由 `add_messages` 合并消息。

应用通过 `graph_builder.compile()` 导出图；接入 Agent Server 后，检查点和 Thread 由服务管理。Notebook 中手动连接 SQLite 的代码不参与 Studio 应用，已有 Notebook 数据也不会自动迁移到 Studio。

本地服务产生的 `.langgraph_api/`、Notebook 产生的 `data/` 和数据库文件均属于本机运行数据，已被忽略。`langgraph dev` 是开发测试服务，不应将这些开发数据作为生产环境的数据保障；正式部署应配置相应的持久化基础设施。

学习用的 `init.ipynb` 保留在作者本地，不包含在 GitHub 仓库中，启动应用不依赖它。

## 常见问题

| 问题 | 检查方式 |
| --- | --- |
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
