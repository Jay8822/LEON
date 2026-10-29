# bg_jobs/queue/watch_queue.ps1
# Added 2026-10-29 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
# A live status window Jay can leave open to watch the compute queue
# himself, so he can catch a problem and flag it sooner instead of
# relying on Claude polling. Read-only -- never touches the job,
# never kills or restarts anything. Safe to close any time; it isn't
# part of the queue itself.

$repoRoot = "C:\Users\jaypr\Desktop\AI Stack"
$statusPath = Join-Path $repoRoot "bg_jobs\queue\out\queue_status.json"
$logPath = Join-Path $repoRoot "bg_jobs\compute_queue.log"

$host.UI.RawUI.WindowTitle = "LEON compute queue -- live status"

while ($true) {
    Clear-Host
    Write-Host "=== LEON compute queue -- live status ===  (updates every 15s, Ctrl+C to close)" -ForegroundColor Cyan
    Write-Host "Checked: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-Host ""

    # --- is the job actually alive and doing something, not just present ---
    $proc = Get-Process python -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) {
        $cpuNow = [math]::Round($proc.CPU, 1)
        $memMb = [math]::Round($proc.WorkingSet / 1MB, 0)
        $runtime = (Get-Date) - $proc.StartTime
        Write-Host "PROCESS: RUNNING -- PID $($proc.Id), up $([math]::Floor($runtime.TotalHours))h $($runtime.Minutes)m, CPU time ${cpuNow}s, memory ${memMb}MB" -ForegroundColor Green
    } else {
        Write-Host "PROCESS: NOT RUNNING -- no python.exe found. If a job should be active, this is worth flagging." -ForegroundColor Red
    }
    Write-Host ""

    # --- which scheduled tasks exist right now (there SHOULDN'T be one --
    # the working convention is: launch, verify, then delete the task
    # definition so nothing can self-retrigger later) ---
    $tasks = schtasks /Query /FO LIST 2>$null | Select-String "TaskName:\s*\\LEON"
    if ($tasks) {
        Write-Host "SCHEDULED TASKS STILL REGISTERED (unexpected once a job is confirmed running):" -ForegroundColor Yellow
        $tasks | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    } else {
        Write-Host "SCHEDULED TASKS: none registered (expected -- the job is fully detached)" -ForegroundColor DarkGray
    }
    Write-Host ""

    # --- per-job outcome, from the queue's own status file ---
    Write-Host "QUEUE STATUS (bg_jobs\queue\out\queue_status.json):"
    if (Test-Path $statusPath) {
        try {
            $status = Get-Content $statusPath -Raw | ConvertFrom-Json
            foreach ($prop in $status.PSObject.Properties) {
                $j = $prop.Value
                $colour = switch ($j.outcome) {
                    "SUCCESS" { "Green" }
                    "RUNNING" { "Cyan" }
                    "FAILED"  { "Red" }
                    default   { "White" }
                }
                $line = "  {0,-28} {1,-8} started {2}" -f $prop.Name, $j.outcome, $j.started_at
                if ($j.finished_at) { $line += " finished $($j.finished_at)" }
                Write-Host $line -ForegroundColor $colour
                if ($j.outcome -eq "FAILED" -and $j.traceback) {
                    $firstLine = ($j.traceback -split "`n") | Where-Object { $_.Trim() -ne "" } | Select-Object -Last 1
                    Write-Host "      -> $firstLine" -ForegroundColor Red
                }
            }
        } catch {
            Write-Host "  (couldn't parse queue_status.json -- might be mid-write, try again in a moment)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  (no status file yet)"
    }
    Write-Host ""

    # --- tail of the raw log, for whatever's actually been flushed ---
    Write-Host "LOG TAIL (bg_jobs\compute_queue.log -- may lag a few minutes, output is buffered):"
    if (Test-Path $logPath) {
        Get-Content $logPath -Tail 6 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    } else {
        Write-Host "  (no log file yet)"
    }

    Write-Host ""
    Write-Host "If PROCESS says NOT RUNNING while a job should be active, or a job shows FAILED," -ForegroundColor DarkYellow
    Write-Host "that's worth flagging to Claude sooner rather than waiting." -ForegroundColor DarkYellow

    Start-Sleep -Seconds 15
}
