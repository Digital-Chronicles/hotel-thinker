@echo off
title Django Make Migrations
color 0A

echo ============================================================
echo Creating fresh migrations...
echo ============================================================
echo.

python manage.py makemigrations

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo ✅ Migrations created successfully!
    echo ============================================================
    echo.
    echo Now run: python manage.py migrate
) else (
    echo.
    echo ============================================================
    echo ❌ Error creating migrations!
    echo ============================================================
)

pause