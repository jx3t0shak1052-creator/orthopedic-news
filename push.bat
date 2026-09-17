@echo off
chcp 65001 > nul
echo.
echo ========================================
echo   orthopedic-news を GitHub に Push
echo ========================================
echo.

cd /d "C:\Users\Masahiro Sato\Documents\GitHub\orthopedic-news"

echo [1/3] 変更をステージング中...
git add .

echo [2/3] コミット中...
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set DATESTR=%datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2%
git commit -m "ニュース更新 %DATESTR%"

echo [3/3] GitHub に Push 中...
git push

echo.
echo ========================================
echo   完了！GitHub Pages に反映されました
echo ========================================
echo.
pause
