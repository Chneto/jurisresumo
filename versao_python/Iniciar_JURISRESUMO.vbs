' ============================================================================
' JURISRESUMO - Inicializador Silencioso para Windows
' Autor: FChNeto
' Finalidade: Inicia o servidor Python e abre o navegador sem tela preta (CMD).
' ============================================================================
Dim WshShell, fso
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Obtem o diretorio do script
Dim scriptDir
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

' Executa o python de forma totalmente oculta (janela = 0)
WshShell.Run "cmd /c python run.py", 0, False

Set WshShell = Nothing
Set fso = Nothing
