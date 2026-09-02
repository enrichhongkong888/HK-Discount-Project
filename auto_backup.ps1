$source = "F:\HK-Discount-Project"
$destination = "F:\BackUp\HK-Discount-Project"

if (!(Test-Path -Path $destination)) {
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
}

Write-Host "執行首次鏡像備份: $source -> $destination" -ForegroundColor Green
robocopy $source $destination /MIR /FFT /R:1 /W:1 /NDL /NFL /NJH /NJS

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $source
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true

$global:lastRun = [DateTime]::MinValue

$action = {
    $now = [DateTime]::Now
    if (($now - $global:lastRun).TotalSeconds -ge 3) {
        $global:lastRun = $now
        robocopy $source $destination /MIR /FFT /R:1 /W:1 /NDL /NFL /NJH /NJS
    }
}

Register-ObjectEvent $watcher "Changed" -Action $action | Out-Null
Register-ObjectEvent $watcher "Created" -Action $action | Out-Null
Register-ObjectEvent $watcher "Deleted" -Action $action | Out-Null
Register-ObjectEvent $watcher "Renamed" -Action $action | Out-Null

Write-Host "即時備份監控中: $source -> $destination" -ForegroundColor Cyan
while ($true) { Start-Sleep -Seconds 2 }
