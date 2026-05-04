@echo off
title Fix __init__.py Files
color 0E

echo ============================================================
echo Restoring missing __init__.py files...
echo ============================================================
echo.

set APPS=accounts hotels rooms bookings finance restaurant bar services store bulk

for %%a in (%APPS%) do (
    if exist "%%a\migrations" (
        if not exist "%%a\migrations\__init__.py" (
            echo Creating: %%a\migrations\__init__.py
            type nul > "%%a\migrations\__init__.py"
            echo   ✅ Created
        ) else (
            echo ✅ %%a\migrations\__init__.py already exists
        )
    ) else (
        echo Creating: %%a\migrations folder...
        mkdir "%%a\migrations"
        type nul > "%%a\migrations\__init__.py"
        echo   ✅ Created
    )
)

echo.
echo ============================================================
echo ✅ All __init__.py files restored!
echo ============================================================
pause