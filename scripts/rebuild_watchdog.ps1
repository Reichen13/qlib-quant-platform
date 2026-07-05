# 全量重建看门狗脚本 v2
# 功能：确保始终有一个重建进程在跑；features 目录停滞超过 8 分钟就杀进程重启（断点续跑自动续上）
# 用法：pwsh -File scripts/rebuild_watchdog.ps1

$ErrorActionPreference = "Continue"
$projectDir = "D:\qlib"
$dataDir = "$env:USERPROFILE\.qlib\qlib_data\cn_data_new"
$stallLimitMin = 8
$checkEverySec = 180
$maxRestarts = 100
$targetTotal = 4481

Set-Location $projectDir
$restarts = 0
$lastCount = -1
$lastChange = Get-Date

function Get-RebuildProc {
    return Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
        $_.StartTime -gt (Get-Date).AddHours(-12) -and $_.CPU -gt 5
    } | Select-Object -First 1
}

function Start-Rebuild {
    $log = "$projectDir\rebuild_full_20260704.log"
    $errLog = "$projectDir\rebuild_full_20260704.err.log"
    $p = Start-Process -FilePath "py" -ArgumentList "-3.12","update_cn_data.py","--full-rebuild","--all","--migrate-instruments","--data-dir",$dataDir -WorkingDirectory $projectDir -RedirectStandardOutput $log -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Write-Output "$(Get-Date -Format 'HH:mm:ss') 启动重建进程 PID=$($p.Id)"
    return $p.Id
}

# 首次：如果没有重建进程在跑，立即启动一个
$proc = Get-RebuildProc
if (-not $proc) {
    Start-Rebuild | Out-Null
    Start-Sleep 20
}

while ($restarts -lt $maxRestarts) {
    $curCount = (Get-ChildItem "$dataDir\features" -Directory -ErrorAction SilentlyContinue | Measure-Object).Count
    if ($curCount -ge $targetTotal) {
        Write-Output "$(Get-Date -Format 'HH:mm:ss') 全量完成: $curCount / $targetTotal"
        break
    }
    $ts = Get-Date -Format 'HH:mm:ss'
    if ($curCount -ne $lastCount) {
        $pct = [math]::Round($curCount/$targetTotal*100,1)
        Write-Output "$ts 进度: $curCount / $targetTotal ($pct%)"
        $lastCount = $curCount
        $lastChange = Get-Date
    } else {
        $stalled = ((Get-Date) - $lastChange).TotalMinutes
        $proc = Get-RebuildProc
        if (-not $proc) {
            Write-Output "$ts 重建进程不存在，重启"
            Start-Rebuild | Out-Null
            $restarts++
            Start-Sleep 20
            $lastChange = Get-Date
            continue
        }
        if ($stalled -gt $stallLimitMin) {
            $sm = [math]::Round($stalled,0)
            Write-Output "$ts 停滞 $sm 分钟且进程卡死，杀进程重启"
            Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -gt (Get-Date).AddHours(-12) -and $_.CPU -gt 5 } | Stop-Process -Force -ErrorAction SilentlyContinue
            Start-Sleep 3
            Start-Rebuild | Out-Null
            $restarts++
            Start-Sleep 25
            $lastChange = Get-Date
            continue
        }
    }
    Start-Sleep $checkEverySec
}
Write-Output "$(Get-Date -Format 'HH:mm:ss') 看门狗结束，总重启 $restarts 次"
