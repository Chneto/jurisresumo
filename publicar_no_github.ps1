# JURISRESUMO - Script de Publicacao no GitHub
# Desenvolvido por FChNeto

Write-Host "======================================================================" -ForegroundColor Green
Write-Host "          JURISRESUMO - Publicador Automatizado no GitHub" -ForegroundColor Green
Write-Host "                     Desenvolvido por FChNeto" -ForegroundColor Green
Write-Host "======================================================================`n"

# 1. Verificar Git
$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCmd) {
    $commonGitPaths = @(
        "$env:LOCALAPPDATA\Programs\Git\cmd",
        "$env:ProgramFiles\Git\cmd",
        "${env:ProgramFiles(x86)}\Git\cmd"
    )
    foreach ($p in $commonGitPaths) {
        if (Test-Path "$p\git.exe") {
            $env:PATH = "$p;$env:PATH"
            $gitCmd = Get-Command git -ErrorAction SilentlyContinue
            break
        }
    }
}

if (-not $gitCmd) {
    Write-Host "[AVISO] Git nao encontrado no PATH do sistema." -ForegroundColor Yellow
    $wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
    if ($wingetCmd) {
        $resp = Read-Host "Deseja instalar o Git automaticamente agora via winget? (S/N)"
        if ($resp -eq 'S' -or $resp -eq 's') {
            Write-Host "Instalando Git via winget..." -ForegroundColor Cyan
            winget install --id Git.Git -e --source winget
            if (Test-Path "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe") {
                $env:PATH = "$env:LOCALAPPDATA\Programs\Git\cmd;$env:PATH"
            }
            $gitCmd = Get-Command git -ErrorAction SilentlyContinue
            Write-Host "`n[OK] Git instalado e carregado!" -ForegroundColor Green
        }
    }
    if (-not $gitCmd) {
        Write-Host "Por favor, instale o Git em https://git-scm.com/ e execute novamente." -ForegroundColor Red
        pause
        exit 1
    }
}

Write-Host "[1/5] Inicializando repositorio Git..." -ForegroundColor Cyan
if (-not (Test-Path ".git")) {
    git init
    git branch -M main
} else {
    Write-Host "      Repositorio Git local ja inicializado."
}

Write-Host "[2/5] Configurando branch principal main..." -ForegroundColor Cyan
git branch -M main

Write-Host "[3/5] Adicionando arquivos da versao..." -ForegroundColor Cyan
git add .

Write-Host "[4/5] Criando commit da versao..." -ForegroundColor Cyan
git commit -m "feat: release v2.2 - JURISRESUMO completo para audiencias criminais (Autor: FChNeto)"

Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "[5/5] Configuracao do Repositorio Remoto no GitHub" -ForegroundColor Green
Write-Host "======================================================================`n"
Write-Host "Cole abaixo o link do seu repositorio criado no GitHub."
Write-Host "Exemplo: https://github.com/seu-usuario/jurisresumo.git`n"
$repoUrl = Read-Host "URL do Repositorio GitHub"

if ([string]::IsNullOrWhiteSpace($repoUrl)) {
    Write-Host "`nNenhuma URL informada. O commit local foi salvo com sucesso!" -ForegroundColor Yellow
    Write-Host "Para conectar ao GitHub mais tarde, execute:"
    Write-Host "   git remote add origin SUA_URL"
    Write-Host "   git push -u origin main`n"
    pause
    exit 0
}

Write-Host "`nConectando ao repositorio remoto..." -ForegroundColor Cyan
git remote remove origin 2>$null
git remote add origin $repoUrl

Write-Host "Enviando projeto para o GitHub..." -ForegroundColor Cyan
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n======================================================================" -ForegroundColor Green
    Write-Host "       [SUCESSO] JURISRESUMO publicado no GitHub com exito!" -ForegroundColor Green
    Write-Host "======================================================================`n"
} else {
    Write-Host "`n[INFO] O envio para o GitHub pode requerer autenticacao no navegador." -ForegroundColor Yellow
    Write-Host "       Execute 'git push -u origin main' caso haja autenticacao pendente.`n"
}
pause
