param(
  [string]$BaseUrl = "https://localhost:8001",
  [string]$Jwt = $env:JWT_TOKEN,
  [string]$Origin = "https://wwwqa.tstation.com",
  [string]$SessionId = ("live-qna-handoff-" + [guid]::NewGuid().ToString("N")),
  [string]$Message = ([string]::Concat(
    [char]0xC0C1, [char]0xB2F4, [char]0xC6D0, [char]0x20,
    [char]0xC5F0, [char]0xACB0, [char]0xD574
  ))
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

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

$bodyPath = Join-Path $env:TEMP ("$SessionId.json")
$outPath = Join-Path $env:TEMP ("$SessionId.sse.txt")

$body = @{
  content    = $Message
  session_id = $SessionId
  stream     = $true
} | ConvertTo-Json -Depth 8

Set-Content -LiteralPath $bodyPath -Encoding UTF8 -Value $body

Write-Host "POST $BaseUrl/api/tstation/messages/chat"
Write-Host "session_id=$SessionId"
Write-Host "message=$Message"
Write-Host ""

curl.exe -k -sS -N "$BaseUrl/api/tstation/messages/chat" `
  -H "Authorization: Bearer $Jwt" `
  -H "Content-Type: application/json" `
  -H "Accept: text/event-stream" `
  -H "Origin: $Origin" `
  --data-binary "@$bodyPath" `
  --max-time 180 |
  Tee-Object -FilePath $outPath | Out-Null

Remove-Item -LiteralPath $bodyPath -ErrorAction SilentlyContinue

Write-Host "--- SSE saved to: $outPath"

$events = @()
Get-Content -LiteralPath $outPath | ForEach-Object {
  if ($_ -like "data: *") {
    $data = $_.Substring(6).Trim()
    if ($data -and $data -ne "[DONE]") {
      try { $events += ($data | ConvertFrom-Json) } catch {}
    }
  }
}

$tools = @($events | Where-Object { $_.type -eq "tool" } | ForEach-Object { $_.tool })
$dataEvents = @($events | Where-Object { $_.type -eq "data" })
$templates = @($dataEvents | ForEach-Object { $_.template })
$messages = @($events | Where-Object { $_.type -eq "message" } | ForEach-Object { $_.content })
$assistantResponses = @($dataEvents | ForEach-Object { $_.data.assistantResponse } | Where-Object { $_ })

$rawStream = Get-Content -LiteralPath $outPath -Raw
$visibleText = ($messages + $assistantResponses) -join "`n"

$hasQnaComplete = $templates -contains "qnaComplete"
$calledTransfer = $tools -contains "transfer_to_qna_tool"
$calledEscalate = $tools -contains "escalate_tool"
$visibleHasUrl = [bool]($visibleText -match "https?://|csexample\.com")
$rawHasFakeUrl = [bool]($rawStream -match "csexample\.com")

Write-Host ""
Write-Host "--- Parsed result ---"
Write-Host "tools=$($tools -join ',')"
Write-Host "templates=$($templates -join ',')"
Write-Host "has_qnaComplete=$hasQnaComplete"
Write-Host "called_transfer_to_qna_tool=$calledTransfer"
Write-Host "called_escalate_tool=$calledEscalate"
Write-Host "visible_text_has_url=$visibleHasUrl"
Write-Host "raw_stream_has_csexample=$rawHasFakeUrl"

Write-Host ""
Write-Host "visible message:"
if ($messages.Count -gt 0) {
  Write-Host ($messages -join "`n")
} else {
  Write-Host "(none)"
}

foreach ($de in $dataEvents) {
  Write-Host ""
  Write-Host "data template=$($de.template)"
  if ($de.data.assistantResponse) {
    Write-Host "assistantResponse=$($de.data.assistantResponse)"
  }
  if ($de.data.redictLink) {
    Write-Host "redictLink.pc=$($de.data.redictLink.pc)"
    Write-Host "redictLink.mobile=$($de.data.redictLink.mobile)"
  }
}

Write-Host ""
Write-Host "--- Checking for qna handoff URL leak bug ---"

$failed = $false

if (-not $hasQnaComplete) {
  Write-Host "FAIL: qnaComplete template was not emitted." -ForegroundColor Red
  $failed = $true
}

if (-not $calledTransfer) {
  Write-Host "FAIL: transfer_to_qna_tool was not called." -ForegroundColor Red
  $failed = $true
}

if ($calledEscalate) {
  Write-Host "FAIL: legacy escalate_tool was called." -ForegroundColor Red
  $failed = $true
}

if ($visibleHasUrl) {
  Write-Host "FAIL: raw URL leaked into visible message or data.assistantResponse." -ForegroundColor Red
  $failed = $true
}

if ($rawHasFakeUrl) {
  Write-Host "FAIL: csexample.com appeared in the SSE stream." -ForegroundColor Red
  $failed = $true
}

if ($failed) {
  Write-Host ""
  Write-Host "LIVE TEST FAILED" -ForegroundColor Red
  exit 1
}

Write-Host "OK: qnaComplete emitted with no fake/raw URL in visible text." -ForegroundColor Green
Write-Host ""
Write-Host "LIVE TEST PASSED" -ForegroundColor Green
exit 0
