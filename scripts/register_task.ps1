# Registers a Windows scheduled task that runs the pipeline every day.
# Run once from the repo root:   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
# Optional:                      ... -File scripts\register_task.ps1 -Time "07:30"
# Remove later with:             Unregister-ScheduledTask -TaskName "UK AI Job Market - daily fetch"
param([string]$Time = "08:00")

$script = Join-Path $PSScriptRoot "run_daily.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
# StartWhenAvailable: if the PC was off at $Time, run as soon as it's next on.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "UK AI Job Market - daily fetch" `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "Fetch UK AI/ML job postings from Adzuna and rebuild the DuckDB tables." -Force
Write-Host "Registered. Logs go to data\logs\. Test it now with: Start-ScheduledTask -TaskName 'UK AI Job Market - daily fetch'"
