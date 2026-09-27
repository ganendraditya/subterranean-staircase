param(
    [Alias('f', 'y', 'yes')]
    [switch]$Force,
    [Alias('purge', 'all')]
    [switch]$RemoveAllData,
    [Parameter(Position = 0)]
    [string]$Action,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$IgnoredArgs
)

# Normalize double-dash flags commonly passed from CLI (e.g., --force, --purge, --all, --yes)
$allArgs = @($Action) + @($IgnoredArgs)
if ($allArgs) {
    if ($allArgs -contains '--force' -or $allArgs -contains '--yes') { $Force = [switch]::Present }
    if ($allArgs -contains '--purge' -or $allArgs -contains '--all') { $RemoveAllData = [switch]::Present }
}

$ErrorActionPreference = "Stop"

$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [Environment]::GetFolderPath([System.Environment+SpecialFolder]::LocalApplicationData) }
$InstallDir = Join-Path $LocalAppData "SubtitleTranslator"
$BinDir = Join-Path (Join-Path $LocalAppData "Programs") "SubtitleTranslator"

$UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath([System.Environment+SpecialFolder]::UserProfile) }
$ConfigDir = if (-not [string]::IsNullOrWhiteSpace($env:XDG_CONFIG_HOME)) { Join-Path $env:XDG_CONFIG_HOME "subtitle-translator" } else { Join-Path (Join-Path $UserHome ".config") "subtitle-translator" }
$CacheDir = if (-not [string]::IsNullOrWhiteSpace($env:XDG_CACHE_HOME)) { Join-Path $env:XDG_CACHE_HOME "subtitle-translator" } else { Join-Path (Join-Path $UserHome ".cache") "subtitle-translator" }

Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "  Subtitle Translator V1 — Windows Uninstaller" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Yellow

if (-not $Force) {
    if (-not [Environment]::UserInteractive) {
        Write-Error "Non-interactive session detected without -Force flag. Aborting."
        exit 1
    }
    $Confirm = Read-Host "Are you sure you want to uninstall Subtitle Translator? [y/N]"
    if ($Confirm -notmatch "^[yY]") {
        Write-Host "Uninstall cancelled."
        exit 0
    }
}

# 1. Remove launcher and clean PATH entry
$LauncherFile = Join-Path $BinDir "subtrans.cmd"
if (Test-Path $LauncherFile) {
    Write-Host "Removing launcher from $BinDir..."
    try {
        Remove-Item -Force $LauncherFile -ErrorAction SilentlyContinue
    } catch {}
}

$regKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
if ($regKey) {
    try {
        $UserPath = $regKey.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        if ($UserPath) {
            $valKind = try { $regKey.GetValueKind('Path') } catch { [Microsoft.Win32.RegistryValueKind]::ExpandString }
            $rawEntries = @($UserPath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
            $NormalizedBin = $BinDir.TrimEnd('\')
            $CleanPaths = $rawEntries |
                Where-Object {
                    $trimmed = $_.TrimEnd('\')
                    $expanded = [System.Environment]::ExpandEnvironmentVariables($_).TrimEnd('\')
                    $trimmed -ine $NormalizedBin -and $expanded -ine $NormalizedBin
                }
            if ($CleanPaths.Count -ne $rawEntries.Count) {
                $NewPath = $CleanPaths -join ';'
                $regKey.SetValue('Path', $NewPath, $valKind)
                $env:Path = ($env:Path -split ';' | Where-Object { $_.TrimEnd('\') -ine $NormalizedBin }) -join ';'
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
                Write-Host "Removed from User PATH."
            }
        }
    } finally {
        $regKey.Close()
    }
}

# 2. Remove Installation Directory
$uninstallFailed = $false
if (Test-Path $InstallDir) {
    Write-Host "Removing application files from $InstallDir..."
    if ($PWD.Path.StartsWith($InstallDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        Set-Location $env:TEMP
        [System.Environment]::CurrentDirectory = $env:TEMP
    }
    try {
        Remove-Item -Recurse -Force $InstallDir -ErrorAction Stop
    } catch {
        $uninstallFailed = $true
        Write-Warning "Could not remove all files in $InstallDir (a file may be in use). Please remove it manually: $InstallDir"
    }
}

# 3. Optional Config & Cache Clean
$ShouldRemoveData = $RemoveAllData
if (-not $ShouldRemoveData) {
    if (-not $Force) {
        $PromptData = Read-Host "Do you also want to remove translation caches and configs? [y/N]"
        if ($PromptData -match "^[yY]") {
            $ShouldRemoveData = $true
        }
    } else {
        Write-Host "Preserved user configs and caches (use -RemoveAllData to remove)."
    }
}

if ($ShouldRemoveData) {
    if (-not [string]::IsNullOrWhiteSpace($ConfigDir) -and (Test-Path $ConfigDir)) {
        try {
            Remove-Item -Recurse -Force $ConfigDir -ErrorAction Stop
        } catch {
            Write-Warning "Could not remove configuration directory: $ConfigDir"
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($CacheDir) -and (Test-Path $CacheDir)) {
        try {
            Remove-Item -Recurse -Force $CacheDir -ErrorAction Stop
        } catch {
            Write-Warning "Could not remove cache directory: $CacheDir"
        }
    }
    Write-Host "Removed user configs and cached models."
}

# Cleanup launcher directory if empty
if ((Test-Path $BinDir) -and -not (Get-ChildItem -Path $BinDir -Force -ErrorAction SilentlyContinue)) {
    try {
        Remove-Item -Path $BinDir -Force -ErrorAction SilentlyContinue
    } catch {}
}

Write-Host ""
if ($uninstallFailed) {
    Write-Warning "Subtitle Translator uninstallation completed with warnings. Some files could not be removed."
} else {
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "✔ Subtitle Translator was cleanly uninstalled." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
}
