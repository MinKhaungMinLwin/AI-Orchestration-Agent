param(
  [string]$BaseUrl = "https://localhost:8001",
  [string]$Jwt = $env:JWT_TOKEN,
  [string]$Origin = "https://wwwqa.tstation.com",
  [string]$SessionId = ("live-qty-chip-" + [guid]::NewGuid().ToString("N")),
  # Edit these to match real catalog/store data in your QA environment.
  [string]$ProductQuery = "235/55R18 벤투스 S2 AS 주문할게",
  [string]$QtyMessage = "2개",
  [string]$StoreOptionMessage = "1",
  [string]$RegionMessage = "강남",
  [string]$StorePickMessage = "1번 매장으로 할게"
)

if (-not $Jwt) {
  # Fall back to repo-root .env (JWT_TOKEN=...) when the shell doesn't have
  # the OS-level env var set — activating the Python venv does not load .env.
  $envFile = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
  if (Test-Path -LiteralPath $envFile) {
    $line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^\s*JWT_TOKEN\s*=' } | Select-Object -First 1
    if ($line) {
      $Jwt = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
      if ($Jwt) {
        Write-Host "Loaded JWT_TOKEN from $envFile" -ForegroundColor DarkGray
      }
    }
  }
}

if (-not $Jwt) {
  Write-Host "Missing JWT. Set it first:" -ForegroundColor Red
  Write-Host '$env:JWT_TOKEN="eyJ..."'
  Write-Host "or add JWT_TOKEN=... to $((Join-Path (Split-Path -Parent $PSScriptRoot) '.env'))"
  exit 2
}

# Ordered user turns that walk the order flow up to the store-schedule step
# where the bug reproduces: STEP1 product -> STEP2 qty -> STEP4 store option
# -> STEP5A region -> STEP5A store pick -> (bug) datepick/quickReply turn.
$Turns = @(
  $ProductQuery,
  $QtyMessage,
  $StoreOptionMessage,
  $RegionMessage,
  $StorePickMessage
)

function Send-Turn {
  param(
    [string]$Message,
    [int]$Index
  )

  $bodyPath = Join-Path $env:TEMP ("$SessionId-turn$Index.json")
  $outPath = Join-Path $env:TEMP ("$SessionId-turn$Index.sse.txt")

  $body = @{
    content    = $Message
    session_id = $SessionId
    stream     = $true
  } | ConvertTo-Json -Depth 8

  Set-Content -LiteralPath $bodyPath -Encoding UTF8 -Value $body

  Write-Host ""
  Write-Host "=== Turn $Index : `"$Message`" ===" -ForegroundColor Cyan

  curl.exe -k -sS -N "$BaseUrl/api/tstation/messages/chat" `
    -H "Authorization: Bearer $Jwt" `
    -H "Content-Type: application/json" `
    -H "Accept: text/event-stream" `
    -H "Origin: $Origin" `
    --data-binary "@$bodyPath" `
    --max-time 180 |
    Tee-Object -FilePath $outPath | Out-Null

  Remove-Item -LiteralPath $bodyPath -ErrorAction SilentlyContinue

  $events = @()
  Get-Content -LiteralPath $outPath | ForEach-Object {
    if ($_ -like "data: *") {
      $data = $_.Substring(6).Trim()
      if ($data -and $data -ne "[DONE]") {
        try { $events += ($data | ConvertFrom-Json) } catch {}
      }
    }
  }
  return $events
}

$allDataEvents = @()

for ($i = 0; $i -lt $Turns.Count; $i++) {
  $events = Send-Turn -Message $Turns[$i] -Index ($i + 1)

  $dataEvents = @($events | Where-Object { $_.type -eq "data" })
  $allDataEvents += $dataEvents

  $tools = @($events | Where-Object { $_.type -eq "tool" } | ForEach-Object { $_.tool })
  $messages = @($events | Where-Object { $_.type -eq "message" } | ForEach-Object { $_.content })

  Write-Host "tools=$($tools -join ',')"
  foreach ($de in $dataEvents) {
    $chipLabels = @($de.data.quickReplies | ForEach-Object { $_.label })
    Write-Host "template=$($de.template) assistantResponse=$($de.data.assistantResponse) chips=[$($chipLabels -join ',')]"
  }
  if ($messages) {
    Write-Host "message: $($messages -join ' | ')"
  }
}

Write-Host ""
Write-Host "--- Checking for the qty-chip/schedule-ask mismatch bug ---"

# Same known-bad chip set that used to get force-injected by the qty
# normalizer regardless of turn context.
$QtyChipSet = @("1개", "2개", "3개", "4개")

$mismatches = @()

foreach ($de in $allDataEvents) {
  if ($de.template -ne "quickReply") { continue }
  $text = [string]$de.data.assistantResponse
  $asksForDateTime = ($text -match "날짜") -and ($text -match "시간")
  if (-not $asksForDateTime) { continue }

  $chipLabels = @($de.data.quickReplies | ForEach-Object { $_.label })
  $isQtyChipSet = ($chipLabels.Count -gt 0) -and (
    (Compare-Object $chipLabels $QtyChipSet -SyncWindow 0).Length -eq 0 -or
    (Compare-Object $chipLabels @("1개","2개") -SyncWindow 0).Length -eq 0
  )

  if ($isQtyChipSet) {
    $mismatches += $de
  }
}

$failed = $false

if ($mismatches.Count -gt 0) {
  Write-Host ""
  Write-Host "FAIL: found quickReply turn asking for date/time but chips are quantity chips:" -ForegroundColor Red
  foreach ($m in $mismatches) {
    Write-Host "  assistantResponse: $($m.data.assistantResponse)"
    Write-Host "  chips: $(($m.data.quickReplies | ForEach-Object { $_.label }) -join ',')"
  }
  $failed = $true
} else {
  Write-Host "OK: no date/time-ask turn carried quantity chips." -ForegroundColor Green
}

# Bonus signal: a correctly-fixed schedule step should render as `datepick`,
# not a generic quickReply, whenever real schedule data was available.
$hasDatepick = @($allDataEvents | Where-Object { $_.template -eq "datepick" }).Count -gt 0
Write-Host "has_datepick_template=$hasDatepick"

if ($failed) {
  Write-Host ""
  Write-Host "LIVE TEST FAILED" -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host "LIVE TEST PASSED" -ForegroundColor Green
exit 0
