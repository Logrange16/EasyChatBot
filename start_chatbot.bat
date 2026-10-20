@echo off
setlocal
chcp 65001 >nul

rem Always run from this project's directory.
cd /d "%~dp0"

rem UTF-8 applies to this launcher and its child processes only.
set "PYTHONUTF8=1"

call "%~dp0scripts\agent_env.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

if not exist "langgraph.json" (
    echo [ERROR] langgraph.json was not found in "%CD%".
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] Missing .env configuration file.
    echo Copy .env.example to .env and fill in your own API keys first.
    pause
    exit /b 1
)

"%AGENT_ENV%\python.exe" -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or later is required'; import langgraph, langgraph_cli, langchain_openai, dotenv"
if errorlevel 1 (
    echo [ERROR] The agent environment is missing required dependencies or uses an unsupported Python version.
    echo Activate agent and run: python -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting ChatBot. Studio will open automatically when the server is ready.
echo Keep this window open while chatting. Press Ctrl+C to stop the server.
echo.

"%AGENT_ENV%\python.exe" -m langgraph_cli dev %*
set "CHATBOT_EXIT_CODE=%ERRORLEVEL%"

if not "%CHATBOT_EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Startup stopped. Check the messages above.
    pause
)

exit /b %CHATBOT_EXIT_CODE%
