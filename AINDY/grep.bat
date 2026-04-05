@echo off
setlocal

set "pattern=%~2"
set "root=%~3"

powershell -NoProfile -Command ^
  "$pattern = $args[0];" ^
  "$root = $args[1];" ^
  "$matches = Get-ChildItem -Path $root -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\tests(\\|$)' } | Select-String -SimpleMatch -Pattern $pattern | Select-Object -ExpandProperty Path -Unique;" ^
  "if ($matches) { $matches; exit 0 } else { exit 1 }" ^
  -- "%pattern%" "%root%"

exit /b %ERRORLEVEL%
