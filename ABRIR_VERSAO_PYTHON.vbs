' ============================================================================
' JURISRESUMO - Inicializador Silencioso da Versão Python (FastAPI + Uvicorn)
' Autor: FChNeto
' Finalidade: Inicia o backend Python na pasta versao_python e abre o navegador
'             sem exibir terminal ou tela preta.
' ============================================================================
Dim WshShell, fso
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

Dim scriptDir
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

Dim pyDir
pyDir = fso.BuildPath(scriptDir, "versao_python")

If fso.FolderExists(pyDir) Then
    WshShell.CurrentDirectory = pyDir
    WshShell.Run "cmd /c python run.py", 0, False
Else
    WshShell.CurrentDirectory = scriptDir
    WshShell.Run "cmd /c python run.py", 0, False
End If

Set WshShell = Nothing
Set fso = Nothing
