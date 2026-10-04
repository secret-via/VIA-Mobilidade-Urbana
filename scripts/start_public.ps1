# Sobe o dashboard VIA local + um túnel público (Cloudflare) na frente dele,
# e mostra a URL de acesso. Fecha os dois (dashboard e túnel) ao sair com Ctrl+C.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$logsDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
$dashboardLog = Join-Path $logsDir "dashboard.out.log"
$dashboardErrLog = Join-Path $logsDir "dashboard.err.log"
$tunnelLog = Join-Path $logsDir "tunnel.out.log"
$tunnelErrLog = Join-Path $logsDir "tunnel.err.log"

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    # Instalado via winget nesta sessão sem reiniciar o terminal - o PATH
    # dessa janela pode ainda não ter sido atualizado, então procura nos
    # locais de instalação padrão do winget antes de desistir.
    $fallbackPaths = @(
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Cloudflare.cloudflared*\cloudflared.exe",
        "C:\Program Files (x86)\cloudflared\cloudflared.exe",
        "C:\Program Files\cloudflared\cloudflared.exe"
    )
    $found = $fallbackPaths | ForEach-Object { Resolve-Path $_ -ErrorAction SilentlyContinue } | Select-Object -First 1
    if ($found) {
        $cloudflared = [pscustomobject]@{ Source = $found.Path }
    } else {
        Write-Host "cloudflared não encontrado. Instale com: winget install --id Cloudflare.cloudflared -e" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Iniciando o dashboard VIA..."
$dashboard = Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList "scripts\dashboard.py" `
    -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $dashboardLog -RedirectStandardError $dashboardErrLog

Start-Sleep -Seconds 5
if ($dashboard.HasExited) {
    Write-Host "O dashboard não conseguiu subir. Veja $dashboardErrLog" -ForegroundColor Red
    Get-Content $dashboardErrLog -Tail 20
    exit 1
}

Write-Host "Abrindo túnel público (Cloudflare)..."
$tunnel = Start-Process -FilePath $cloudflared.Source -ArgumentList "tunnel", "--url", "http://127.0.0.1:5000" `
    -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $tunnelLog -RedirectStandardError $tunnelErrLog

# cloudflared imprime o progresso (inclusive a URL do túnel) no stderr, não no stdout.
$url = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $tunnelErrLog) {
        $match = Select-String -Path $tunnelErrLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($match) { $url = $match.Matches[0].Value; break }
    }
}

Write-Host ""
if ($url) {
    Write-Host "===================================================="
    Write-Host " VIA disponível publicamente em:"
    Write-Host " $url"
    Write-Host "===================================================="
} else {
    Write-Host "Não consegui capturar a URL do túnel a tempo. Veja $tunnelErrLog" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Essa URL muda toda vez que você roda este script (túnel gratuito, sem conta)."
Write-Host "Pressione Ctrl+C nesta janela para encerrar o dashboard e o túnel."
Write-Host ""

try {
    Wait-Process -Id $dashboard.Id
} finally {
    Write-Host "Encerrando..."
    Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $dashboard.Id -Force -ErrorAction SilentlyContinue
}
