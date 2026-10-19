@echo off
setlocal
chcp 65001 >nul

rem Always run from this project's directory.
cd /d "%~dp0"

rem UTF-8 applies to this launcher and its child processes only.
set "PYTHONUTF8=1"

rem Use the agent interpreter directly; no interactive conda activation needed.
rem AGENT_ENV may also be supplied explicitly for a custom environment location.
if not defined AGENT_ENV if /i "%CONDA_DEFAULT_ENV%"=="agent" set "AGENT_ENV=%CONDA_PREFIX%"

rem Look beside the Conda installation when its location is already known.
if not defined AGENT_ENV if defined CONDA_EXE (
    for %%I in ("%CONDA_EXE%") do (
        if exist "%%~dpI..\envs\agent\python.exe" for %%E in ("%%~dpI..\envs\agent") do set "AGENT_ENV=%%~fE"
        if exist "%%~dpIenvs\agent\python.exe" for %%E in ("%%~dpIenvs\agent") do set "AGENT_ENV=%%~fE"
    )
)

rem Common user and system installation locations.
if not defined AGENT_ENV (
    for %%E in ("%USERPROFILE%\.conda\envs\agent" "%USERPROFILE%\miniconda3\envs\agent" "%USERPROFILE%\anaconda3\envs\agent" "%LOCALAPPDATA%\miniconda3\envs\agent" "%LOCALAPPDATA%\anaconda3\envs\agent" "%ProgramData%\miniconda3\envs\agent" "%ProgramData%\anaconda3\envs\agent") do (
        if exist "%%~E\python.exe" set "AGENT_ENV=%%~E"
    )
)

rem Ask Conda as a fallback for environments stored in another location.
if not defined AGENT_ENV (
    for /f "delims=" %%E in ('conda run -n agent python -c "import sys; print(sys.prefix)" 2^>nul') do set "AGENT_ENV=%%E"
)

if not exist "%AGENT_ENV%\python.exe" (
    echo [ERROR] Could not find the agent Python environment.
    echo Create it first, or activate agent in Anaconda Prompt and run this file again.
    echo For a custom location, set AGENT_ENV to the environment directory.
    pause
    exit /b 1
)
set "PATH=%AGENT_ENV%;%AGENT_ENV%\Library\mingw-w64\bin;%AGENT_ENV%\Library\usr\bin;%AGENT_ENV%\Library\bin;%AGENT_ENV%\Scripts;%AGENT_ENV%\bin;%PATH%"

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
