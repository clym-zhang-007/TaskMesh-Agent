@echo off
echo ========================================
echo Agent Loop 诊断工具
echo ========================================
echo.

echo [1/3] 检查后端是否运行...
curl -s http://localhost:8000/api/health >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ 后端正在运行
    curl http://localhost:8000/api/health
) else (
    echo ❌ 后端未运行
    echo.
    echo 请先启动后端：
    echo   .\start_backend.bat
    goto :end
)

echo.
echo [2/3] 检查对话列表 API...
curl -s http://localhost:8000/api/conversations
echo.

echo.
echo [3/3] 检查前端是否运行...
curl -s http://localhost:5173 >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ 前端正在运行
) else (
    echo ❌ 前端未运行
    echo.
    echo 请启动前端：
    echo   .\start_frontend.bat
)

:end
echo.
echo ========================================
echo 诊断完成
echo ========================================
echo.
echo 如果后端和前端都在运行，请：
echo 1. 重启前端（Ctrl+C 然后重新运行 start_frontend.bat）
echo 2. 清除浏览器缓存
echo 3. 访问 http://localhost:5173
echo.
pause
