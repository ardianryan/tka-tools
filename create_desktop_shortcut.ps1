# Buat shortcut di Desktop Windows dengan icon Smart TKA Scanner
$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutPath = Join-Path $DesktopPath "Smart TKA Scanner.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = (Join-Path $PSScriptRoot "run_dashboard.bat")
$Shortcut.WorkingDirectory = $PSScriptRoot
$Shortcut.IconLocation = (Join-Path $PSScriptRoot "app_icon.ico")
$Shortcut.Description = "Smart TKA Scanner & Auto-Uploader Kemendikdasmen"
$Shortcut.Save()
Write-Host "Shortcut berhasil dibuat di: $ShortcutPath"
