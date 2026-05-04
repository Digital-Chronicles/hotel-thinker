@echo off
title Full Django Reset
color 0C

echo ============================================================
echo FULL DATABASE RESET
echo ============================================================
echo WARNING: This will delete everything!
echo.
set /p confirm="Type 'FULL RESET' to continue: "

if not "%confirm%"=="FULL RESET" (
    echo.
    echo Cancelled.
    pause
    exit /b
)

echo.
echo Starting full reset process...
echo.

REM Step 1: Reset migrations
call reset_migrations.bat

REM Step 2: Create new migrations
echo.
call make_migrations.bat

REM Step 3: Apply migrations
echo.
call migrate.bat

REM Step 4: Create superuser
echo.
call create_superuser.bat

echo.
echo ============================================================
echo ✅ FULL RESET COMPLETE!
echo ============================================================
echo.
echo Your database is now ready to use.
echo You can now run: python manage.py runserver
echo.
pause