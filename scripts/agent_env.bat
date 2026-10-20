@echo off
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
    exit /b 1
)
set "PATH=%AGENT_ENV%;%AGENT_ENV%\Library\mingw-w64\bin;%AGENT_ENV%\Library\usr\bin;%AGENT_ENV%\Library\bin;%AGENT_ENV%\Scripts;%AGENT_ENV%\bin;%PATH%"

exit /b 0
