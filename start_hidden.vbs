Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
strPath = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

strPythonw = strPath & "\venv\Scripts\pythonw.exe"
If FSO.FileExists(strPythonw) Then
    WshShell.Run """" & strPythonw & """ bot.py", 0, False
Else
    WshShell.Run "cmd /c py -3 -m bot", 0, False
End If
