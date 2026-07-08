param(
  [string]$BaseUrl = "https://localhost:8001",
  [string]$Jwt = $env:JWT_TOKEN,
  [string]$Origin = "https://wwwqa.tstation.com",
  [string]$SessionId = ("live-qty-chip-" + [guid]::NewGuid().ToString("N")),
  # Edit these to match real catalog/store data in your QA environment.
  # This default sequence is a verified-working path on chat_v3: an unmatched
  # size search -> browse all products -> pick product+qty together -> give a
  # region -> pick a store. Turn 3 is where ord_qty first gets resolved.
  [string]$ProductQuery = "235/55R18 벤투스 S2 AS 주문할게",
  [string]$BrowseAllMessage = "전체 상품보기",
  [string]$ProductAndQtyMessage = "1번 다이나프로 HL3로 2개 주문할게",
  [string]$RegionMessage = "한남",
  [string]$StorePickMessage = "1번 매장으로 할게",
  # 1-based index into $Turns of the message that first resolves ord_qty.
  # From that turn's response onward, qty chips must never reappear.
  [int]$QtyResolvedFromTurn = 3
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

$Turns = @(
  $ProductQuery,
  $BrowseAllMessage,
  $ProductAndQtyMessage,
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

# Same fixed chip vocabulary chat_v3/templates.py:_QUANTITY_CHIPS emits.
$QtyChipSet = @("1개", "2개", "3개", "4개")

$allTurnResults = @()

for ($i = 0; $i -lt $Turns.Count; $i++) {
  $turnNumber = $i + 1
  $events = Send-Turn -Message $Turns[$i] -Index $turnNumber

  $dataEvents = @($events | Where-Object { $_.type -eq "data" })
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

  $allTurnResults += [pscustomobject]@{
    TurnNumber = $turnNumber
    DataEvents = $dataEvents
  }
}

Write-Host ""
Write-Host "--- Checking: once ord_qty is resolved, qty chips must never reappear ---"
Write-Host "qty_resolved_from_turn=$QtyResolvedFromTurn (chat_v3/templates.py quantity_quick_replies gates on slots.ord_qty)"

$mismatches = @()

foreach ($turnResult in $allTurnResults) {
  if ($turnResult.TurnNumber -lt $QtyResolvedFromTurn) { continue }
  foreach ($de in $turnResult.DataEvents) {
    if ($de.template -ne "quickReply") { continue }
    $chipLabels = @($de.data.quickReplies | ForEach-Object { $_.label })
    if ($chipLabels.Count -eq 0) { continue }
    $isQtyChipSet = (Compare-Object $chipLabels $QtyChipSet -SyncWindow 0).Length -eq 0
    if ($isQtyChipSet) {
      $mismatches += [pscustomobject]@{
        TurnNumber        = $turnResult.TurnNumber
        AssistantResponse = $de.data.assistantResponse
        Chips             = $chipLabels
      }
    }
  }
}

$failed = $false

if ($mismatches.Count -gt 0) {
  Write-Host ""
  Write-Host "FAIL: quantity chips reappeared after ord_qty was already resolved:" -ForegroundColor Red
  foreach ($m in $mismatches) {
    Write-Host "  turn $($m.TurnNumber): $($m.AssistantResponse)"
    Write-Host "  chips: $($m.Chips -join ',')"
  }
  $failed = $true
} else {
  Write-Host "OK: no quickReply turn after qty resolution carried quantity chips." -ForegroundColor Green
}

# Bonus signal: a correctly-handled schedule step should render as `datepick`
# (chat_v3/templates.py _TOOL_TEMPLATES maps get_store_schedule_tool -> datepick)
# rather than falling back to a generic quickReply.
$allDataEvents = @($allTurnResults | ForEach-Object { $_.DataEvents })
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
