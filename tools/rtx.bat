@echo off
rem SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
rem SPDX-License-Identifier: Apache-2.0

setlocal
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
where uv >nul 2>nul
if errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>nul
if errorlevel 1 (
    echo uv installation failed. Install uv 0.13 or newer and try again.
    exit /b 1
)
set "PYTHONUNBUFFERED=1"
uv run rtx %*
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
