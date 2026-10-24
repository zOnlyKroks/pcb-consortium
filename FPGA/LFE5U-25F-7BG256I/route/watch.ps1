# Freerouting progress: reads only the end of the (huge, warning-flooded) log every 30 s.
# Usage: powershell -ExecutionPolicy Bypass -File route\watch.ps1      (-Once: print the current state and exit)
param([switch]$Once)
$f = "$env:LOCALAPPDATA\freerouting\logs\freerouting.log"
$seen = @{}
$first = $true
while ($true) {
    $fs = [IO.File]::Open($f, 'Open', 'Read', 'ReadWrite')
    $back = if ($first) { 200MB } else { 40MB }
    [void]$fs.Seek([Math]::Max(0, $fs.Length - $back), 'Begin')
    $txt = (New-Object IO.StreamReader($fs)).ReadToEnd()
    $fs.Close()
    $hits = [regex]::Matches($txt, '(?m)^\S+ (\d\d:\d\d:\d\d)\S* INFO +\[([^\]]+)\] (Auto-routing pass #(\d+).*?\((\d+) unrouted|Fanout stage completed|Auto-routing stage completed.*?\((\d+) unrouted|Job .* finished).*$')
    $job = if ($hits.Count) { $hits[$hits.Count - 1].Groups[2].Value } else { '' }
    foreach ($m in $hits) {
        if ($m.Groups[2].Value -ne $job -or $seen.ContainsKey($m.Value)) { continue }
        $seen[$m.Value] = 1
        $t = $m.Groups[1].Value
        if ($m.Groups[4].Success) { "$t  pass $($m.Groups[4].Value): $($m.Groups[5].Value) unrouted" }
        elseif ($m.Groups[6].Success) { "$t  DONE: $($m.Groups[6].Value) unrouted, saving .ses" }
        elseif ($m.Value -match 'Fanout') { "$t  fan-out stage done, routing passes start" }
        else { "$t  job finished" }
    }
    $first = $false
    if ($Once) { break }
    Start-Sleep 30
}
