@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
call "%~dp0scripts\agent_env.bat"
if errorlevel 1 (
    pause
    exit /b 1
)
if not exist ".env" (
    echo [ERROR] Copy .env.example to .env and fill in QWEN_API_KEY and CHAT_PASSWORD first.
    pause
    exit /b 1
)
"%AGENT_ENV%\python.exe" -c "import starlette, uvicorn, aiosqlite; from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver"
if errorlevel 1 (
    echo [ERROR] Activate agent and run: python -m pip install -r requirements.txt
    pause
    exit /b 1
)
echo Starting your web chat. Keep this window open while chatting.
echo.
"%AGENT_ENV%\python.exe" "%~dp0run_web.py" %*
set "CHATBOT_EXIT_CODE=%ERRORLEVEL%"
if not "%CHATBOT_EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] The web chat stopped. Check the messages above.
    pause
)
exit /b %CHATBOT_EXIT_CODE%
