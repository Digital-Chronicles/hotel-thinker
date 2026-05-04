@echo off
title Django Migrations Reset
color 0C

echo ============================================================
echo WARNING: This will delete ALL migrations and your database!
echo ============================================================
echo.
set /p confirm="Type 'yes' to continue: "

if not "%confirm%"=="yes" (
    echo.
    echo Cancelled.
    pause
    exit /b
)

echo.
echo ============================================================
echo Step 1: Deleting migration files...
echo ============================================================

REM List of your apps
set APPS=accounts hotels rooms bookings finance restaurant bar services store bulk

for %%a in (%APPS%) do (
    if exist "%%a\migrations" (
        echo Cleaning %%a\migrations...
        
        REM Delete all .py files except __init__.py
        for %%f in ("%%a\migrations\*.py") do (
            if not "%%~nxf"=="__init__.py" (
                echo   Deleting: %%f
                del /q "%%f"
            )
        )
        
        REM Delete .pyc files
        if exist "%%a\migrations\*.pyc" del /q "%%a\migrations\*.pyc"
        
        REM Delete __pycache__ folder
        if exist "%%a\migrations\__pycache__" (
            echo   Deleting: %%a\migrations\__pycache__
            rmdir /s /q "%%a\migrations\__pycache__"
        )
        
        REM Ensure __init__.py exists
        if not exist "%%a\migrations\__init__.py" (
            echo   Creating: %%a\migrations\__init__.py
            type nul > "%%a\migrations\__init__.py"
        )
        
        echo   ✅ Done with %%a
        echo.
    ) else (
        echo ⚠️  %%a\migrations not found, creating...
        mkdir "%%a\migrations"
        type nul > "%%a\migrations\__init__.py"
        echo   ✅ Created %%a\migrations with __init__.py
        echo.
    )
)

echo.
echo ============================================================
echo Step 2: Deleting database...
echo ============================================================

if exist "db.sqlite3" (
    echo Deleting db.sqlite3...
    del /q "db.sqlite3"
    echo ✅ Database deleted
) else (
    echo ⚠️  Database file not found
)

echo.
echo ============================================================
echo Step 3: Cleaning Python cache files...
echo ============================================================

for /d /r . %%d in (__pycache__) do (
    if exist "%%d" (
        echo Deleting: %%d
        rmdir /s /q "%%d"
    )
)

echo.
echo ============================================================
echo ✅ RESET COMPLETE!
echo ============================================================
echo.
echo Now run:
echo   1. python manage.py makemigrations
echo   2. python manage.py migrate
echo   3. python manage.py createsuperuser
echo.
pause