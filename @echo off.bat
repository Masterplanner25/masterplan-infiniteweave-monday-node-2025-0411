@echo off
echo ================================
echo   🧠 A.I.N.D.Y. Git Health Check
echo ================================
echo.

:: Move into the correct repo path (optional)
cd /d "C:\Users\world\OneDrive\Documents\A.I.N.D.Y"

:: 1️⃣ Fetch latest from remote
echo 🔄 Fetching latest remote info...
git fetch origin main >nul 2>&1

:: 2️⃣ Show current branch and status
echo 📦 Branch and Status:
git status -sb
echo.

:: 3️⃣ Compare local HEAD vs remote
echo 🧩 Comparing commits...
for /f %%a in ('git rev-parse HEAD') do set LOCAL=%%a
for /f %%a in ('git rev-parse origin/main') do set REMOTE=%%a

echo Local HEAD:  %LOCAL%
echo Remote main: %REMOTE%
echo.

if "%LOCAL%"=="%REMOTE%" (
    echo ✅ Commits match perfectly.
) else (
    echo ⚠️  Commits differ! You may need to pull or push.
)

:: 4️⃣ Check for file-level differences
echo.
echo 🔍 Checking for uncommitted or unstaged changes...
git diff --stat HEAD origin/main
echo.

:: 5️⃣ Check for untracked files
git status --short | find "??" >nul
if %errorlevel%==0 (
    echo ⚠️  Untracked files detected.
) else (
    echo ✅ No untracked files.
)

echo.
echo 🧹 Tip: Run "git clean -fdx" only when you're sure it's safe to remove untracked files.
echo.
echo 🧩 Health check complete!
pause
