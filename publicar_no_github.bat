@echo off
chcp 65001 >nul
title JURISRESUMO - Publicador no GitHub
color 0A

echo ======================================================================
echo          JURISRESUMO - Publicador Automatizado no GitHub
echo                     Desenvolvido por FChNeto
echo ======================================================================
echo.

:: 1. Verificar se o Git esta instalado ou localiza-lo em caminhos padrao
where git >nul 2>nul
if %errorlevel% neq 0 (
    if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" (
        set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%PATH%"
    ) else if exist "%ProgramFiles%\Git\cmd\git.exe" (
        set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
    ) else if exist "C:\Program Files (x86)\Git\cmd\git.exe" (
        set "PATH=C:\Program Files (x86)\Git\cmd;%PATH%"
    )
)

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [AVISO] O Git nao foi encontrado no sistema.
    echo Tentando verificar o gerenciador de pacotes winget...
    where winget >nul 2>nul
    if %errorlevel% equ 0 (
        echo.
        echo Deseja instalar o Git automaticamente agora via winget? (S/N)
        set /p INSTALAR=
        if /i "%INSTALAR%"=="S" (
            echo Instalando o Git... Aguarde...
            winget install --id Git.Git -e --source winget
            if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%PATH%"
            if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
            echo.
            echo [OK] Instalacao do Git concluida.
        )
    )
    where git >nul 2>nul
    if %errorlevel% neq 0 (
        echo.
        echo Por favor, instale o Git atraves de: https://git-scm.com/
        pause
        exit /b 1
    )
)

echo [1/5] Inicializando repositorio Git local...
if not exist ".git" (
    git init
    git branch -M main
) else (
    echo       Repositorio Git ja existente.
)

echo [2/5] Configurando branch principal main...
git branch -M main

echo [3/5] Adicionando arquivos da versao...
git add .

echo [4/5] Criando commit da versao...
git commit -m "feat: release v2.2 - JURISRESUMO completo para audiencias criminais (Autor: FChNeto)"

echo.
echo ======================================================================
echo [5/5] Configuracao do Repositorio Remoto no GitHub
echo ======================================================================
echo.
echo Cole abaixo o link do seu repositorio criado no GitHub.
echo Exemplo: https://github.com/seu-usuario/jurisresumo.git
echo.
set /p REPO_URL="URL do Repositorio GitHub: "

if "%REPO_URL%"=="" (
    echo.
    echo Nenhuma URL informada. O commit local foi salvo com sucesso!
    echo Quando criar seu repositorio no GitHub, execute:
    echo    git remote add origin SUA_URL
    echo    git push -u origin main
    echo.
    pause
    exit /b 0
)

echo.
echo Conectando ao repositorio remoto...
git remote remove origin >nul 2>nul
git remote add origin %REPO_URL%

echo Enviando projeto para o GitHub...
git push -u origin main

echo.
if %errorlevel% equ 0 (
    echo ======================================================================
    echo       [SUCESSO] JURISRESUMO publicado no GitHub com exito!
    echo ======================================================================
) else (
    echo [INFO] O envio para o GitHub pode requerer login no seu navegador.
    echo        Tente rodar 'git push -u origin main' caso haja autenticacao pendente.
)

echo.
pause
