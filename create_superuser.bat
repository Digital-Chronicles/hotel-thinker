@echo off
title Django Create Superuser
color 0A

echo ============================================================
echo Creating superuser...
echo ============================================================
echo.

python manage.py createsuperuser

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo ✅ Superuser created successfully!
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo ❌ Error creating superuser!
    echo ============================================================
)

pause