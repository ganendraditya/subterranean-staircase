# Subtitle Translator V1 — Single-line Terminal Installer (Windows PowerShell)
$ErrorActionPreference = "Stop"

$AppName = "subtrans"
$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [Environment]::GetFolderPath([System.Environment+SpecialFolder]::LocalApplicationData) }
$InstallDir = Join-Path $LocalAppData "SubtitleTranslator"
$BinDir = Join-Path (Join-Path $LocalAppData "Programs") "SubtitleTranslator"
$RepoUrl = "https://github.com/ganendraditya/subterranean-staircase.git"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Subterranean Staircase / Subtitle Translator" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Check Python (requires Python 3.10 - 3.12 for ONNX/PyTorch compatibility)
$PyExe = $null
$PyVersion = $null
$candidates = Get-Command python3.12.exe, python3.11.exe, python3.10.exe, python.exe, py.exe -ErrorAction SilentlyContinue
foreach ($cmd in $candidates) {
    $exe = if ($cmd.Path) { $cmd.Path } elseif ($cmd.Source) { $cmd.Source } else { $cmd.Definition }
    $ver = if ($exe) { & $exe -c "import sys; sys.exit(1) if not (3, 10) <= sys.version_info < (3, 13) else print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null } else { $null }
    if ($ver) {
        $PyExe = $exe
        $PyVersion = $ver
        break
    }
}

if (-not $PyVersion) {
    Write-Error "Python 3.10, 3.11, or 3.12 is required (ONNX runtime and CTranslate2 do not yet support Python 3.13+). Please install Python 3.11 or 3.12."
    exit 1
}

# 2. Check Git
$GitCmd = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $GitCmd) {
    Write-Error "Git is required but was not found in PATH. Please install Git from git-scm.com"
    exit 1
}

# 3. Clone or update repository
if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Host "Updating existing installation in $InstallDir..."
    git -C $InstallDir pull --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Git pull encountered issues. Resetting to remote state (stashing local changes)..."
        git -C $InstallDir stash --quiet 2>$null
        git -C $InstallDir fetch --quiet origin
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to fetch repository from origin."
            exit 1
        }
        $upstream = git -C $InstallDir rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>$null
        if (-not $upstream -or $LASTEXITCODE -ne 0) {
            $upstream = (git -C $InstallDir rev-parse FETCH_HEAD 2>$null) | Select-Object -First 1
            if (-not $upstream -or $LASTEXITCODE -ne 0) { $upstream = "HEAD" }
        }
        git -C $InstallDir reset --hard $upstream --quiet
        Write-Warning "Local modifications were stashed. You can inspect or restore them using 'git -C \`"$InstallDir\`" stash pop'."
    }
} else {
    if (Test-Path $InstallDir) {
        if ((Get-ChildItem -Path $InstallDir -Force -ErrorAction SilentlyContinue).Count -gt 0) {
            Write-Warning "Target directory $InstallDir already exists and is not a valid Git repository."
            if (-not [Environment]::UserInteractive) {
                Write-Error "Target directory exists and session is non-interactive. Installation aborted."
                exit 1
            }
            $Confirm = Read-Host "Do you want to overwrite it? [y/N]"
            if ($Confirm -notmatch "^[yY]") {
                Write-Error "Installation aborted."
                exit 1
            }
        }
        Remove-Item -Recurse -Force $InstallDir
    }
    Write-Host "Cloning repository into $InstallDir..."
    git clone --quiet --depth 1 $RepoUrl $InstallDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to clone repository from $RepoUrl."
        exit 1
    }
}

# 4. Setup Virtual Environment
$VenvDir = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPyVer = if (Test-Path $VenvPython) { & $VenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null } else { $null }

if (-not (Test-Path $VenvPython) -or ($VenvPyVer -ne $PyVersion)) {
    Write-Host "Creating virtual environment with Python $PyVersion in $VenvDir..."
    if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
    & $PyExe -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment."
        exit 1
    }
}

Write-Host ""
Write-Host "📦 Installing AI & GUI dependencies (RapidOCR, CTranslate2, PyQt6)..." -ForegroundColor Cyan
Write-Host "--------------------------------------------------" -ForegroundColor DarkGray

$MirrorArgs = @()
try {
    $resp = Invoke-WebRequest -Uri "https://mirrors.aliyun.com/pypi/simple/" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($resp.StatusCode -eq 200) {
        Write-Host "✔ Using high-speed Regional PyPI CDN mirror" -ForegroundColor Green
        $MirrorArgs = @("-i", "https://mirrors.aliyun.com/pypi/simple/", "--trusted-host", "mirrors.aliyun.com")
    }
} catch {}

& $VenvPython -m pip install @MirrorArgs --upgrade pip --quiet
& $VenvPython -m pip install @MirrorArgs -r (Join-Path $InstallDir "requirements.txt") |
    Where-Object { $_ -match "^(Downloading|Installing collected packages|Successfully installed|ERROR)" }

Write-Host "--------------------------------------------------" -ForegroundColor DarkGray

# 5. Create launcher batch script in bin directory
if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
}

$EscapedInstallDir = $InstallDir.Replace('%', '%%')
$LauncherPath = Join-Path $BinDir "subtrans.cmd"
$LauncherContent = @"
@echo off
setlocal DisableDelayedExpansion
set "INSTALL_DIR=$EscapedInstallDir"
if /I "%~1"=="uninstall" goto :do_uninstall

"%INSTALL_DIR%\.venv\Scripts\python.exe" "%INSTALL_DIR%\run.py" %*
exit /b %ERRORLEVEL%

:do_uninstall
set "TMP_UNINSTALL=%TEMP%\subtrans_uninstall_%RANDOM%.ps1"
copy /Y "%INSTALL_DIR%\uninstall.ps1" "%TMP_UNINSTALL%" >nul 2>&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%TMP_UNINSTALL%" %*
set "EXIT_CODE=%ERRORLEVEL%"
del /f /q "%TMP_UNINSTALL%" >nul 2>&1
exit /b %EXIT_CODE%
"@
$LauncherContent = $LauncherContent -replace "(?<!\r)\n", "`r`n"

[System.IO.File]::WriteAllText($LauncherPath, $LauncherContent, [System.Text.UTF8Encoding]::new($false))
Write-Host "✔ Created launcher: $LauncherPath" -ForegroundColor Green

# 6. Add to User PATH if not already present
$regKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
if ($regKey) {
    try {
        $UserPath = $regKey.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        $valKind = try { $regKey.GetValueKind('Path') } catch { [Microsoft.Win32.RegistryValueKind]::ExpandString }
        $PathEntries = if ($UserPath) { $UserPath -split ';' | Where-Object { $_ } } else { @() }
        $NormalizedBin = $BinDir.TrimEnd('\')
        if (-not ($PathEntries | Where-Object { [System.Environment]::ExpandEnvironmentVariables($_).TrimEnd('\') -ieq $NormalizedBin })) {
            Write-Host "Adding $BinDir to User PATH..."
            $NewUserPath = ($PathEntries + $BinDir) -join ';'
            $regKey.SetValue('Path', $NewUserPath, $valKind)
            $env:Path = "$env:Path;$BinDir"

            # Broadcast WM_SETTINGCHANGE so new shells inherit the updated PATH without requiring a logout
            try {
                $HWND_BROADCAST = [IntPtr]0xffff
                $WM_SETTINGCHANGE = 0x001A
                $result = [IntPtr]::Zero
                if (-not ('Win32.NativeMethods' -as [type])) {
                    try {
                        Add-Type -Namespace Win32 -Name NativeMethods -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("user32.dll", SetLastError = true, CharSet = System.Runtime.InteropServices.CharSet.Auto)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out IntPtr lpdwResult);
'@ -ErrorAction SilentlyContinue
                    } catch {}
                }
                if ('Win32.NativeMethods' -as [type]) {
                    [Win32.NativeMethods]::SendMessageTimeout($HWND_BROADCAST, $WM_SETTINGCHANGE, [UIntPtr]::Zero, "Environment", 2, 5000, [ref]$result) | Out-Null
                }
            } catch {}
        }
    } finally {
        $regKey.Close()
    }
}

# 7. Configure Windows Startup Shortcut (auto-start subtrans on login)
$StartupDir = [Environment]::GetFolderPath([System.Environment+SpecialFolder]::Startup)
$StartupShortcut = Join-Path $StartupDir "subtrans.cmd"

try {
    $StartupContent = "@echo off`r`nstart `"`" `"$LauncherPath`"`r`n"
    [System.IO.File]::WriteAllText($StartupShortcut, $StartupContent, [System.Text.UTF8Encoding]::new($false))
    Write-Host "✔ Configured background service — subtrans will standby at login." -ForegroundColor Green
} catch {
    Write-Warning "Could not write startup shortcut: $_"
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "✔ Installation completed successfully!" -ForegroundColor Green
Write-Host "Run 'subtrans' to launch Subtitle Translator." -ForegroundColor Green
Write-Host "Run 'subtrans uninstall' to remove it." -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green

# Auto-launch app into background immediately after install if not already running
$runningApp = Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*SubtitleTranslator*" }
if (-not $runningApp) {
    Write-Host "🚀 Starting Subterranean Staircase in your System Tray..." -ForegroundColor Cyan
    Start-Process -FilePath $LauncherPath -WindowStyle Hidden
}
