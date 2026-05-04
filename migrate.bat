@echo off
title Django Migrate
color 0A

echo ============================================================
echo Running migrations...
echo ============================================================
echo.

python manage.py migrate

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo ✅ Migrations applied successfully!
    echo ============================================================
    echo.
    echo Now run: python manage.py createsuperuser
) else (
    echo.
    echo ============================================================
    echo ❌ Error applying migrations!
    echo ============================================================
)

pause