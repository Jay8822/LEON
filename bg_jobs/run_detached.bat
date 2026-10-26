@echo off
REM run_detached.bat <job_name> <python_module>
REM Runs `python -m <python_module>` from the repo root, fully
REM detached from any parent process (launched via schtasks, which
REM runs under the Task Scheduler service's own process tree -- it
REM survives the Claude Code session, the terminal, or bash.exe
REM closing or crashing). Logs to bg_jobs\<job_name>.log and writes
REM bg_jobs\<job_name>.exitcode when done (0 = success).
cd /d "C:\Users\jaypr\Desktop\AI Stack"
python -m %2 > "bg_jobs\%1.log" 2>&1
echo %ERRORLEVEL% > "bg_jobs\%1.exitcode"
