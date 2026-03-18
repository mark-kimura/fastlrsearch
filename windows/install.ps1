# FastLRSearch Windows Installer
#
# Usage (open PowerShell and paste):
#   powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/mark-kimura/fastlrsearch/master/windows/install.ps1 -OutFile $env:TEMP\fastlrsearch-install.ps1; & $env:TEMP\fastlrsearch-install.ps1"
#
# Or after cloning:
#   powershell -ExecutionPolicy Bypass -File windows\install.ps1
#
# What this does:
#   1. Installs Git (if not installed)
#   2. Installs Python 3.12 (if not installed)
#   3. Clones/updates FastLRSearch
#   4. Creates virtual environment and installs dependencies
#   5. Creates Start Menu shortcut and CLI wrapper
#   6. Optionally installs the Lightroom plugin

$ErrorActionPreference = "Stop"

$APP_NAME = "FastLRSearch"
$INSTALL_DIR = Join-Path $env:LOCALAPPDATA "fastlrsearch"
$VENV_DIR = Join-Path $INSTALL_DIR "venv"
$REPO_URL = "https://github.com/mark-kimura/fastlrsearch.git"
$REPO_DIR = Join-Path $INSTALL_DIR "repo"
$LOG_DIR = Join-Path $INSTALL_DIR "logs"

# -- Step 0: Banner and logging ----------------------------------
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null
$LOG_FILE = Join-Path $LOG_DIR "install.log"

try { Start-Transcript -Path $LOG_FILE -Append } catch { }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  $APP_NAME Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "OS:         $([System.Environment]::OSVersion.VersionString)"
Write-Host "PowerShell: $($PSVersionTable.PSVersion)"
Write-Host "Log:        $LOG_FILE"
Write-Host ""

# -- Helper: Refresh PATH from registry --------------------------
function Refresh-Path {
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:PATH = "$machinePath;$userPath"
}

# -- Helper: Check if winget is available -------------------------
function Test-Winget {
    try {
        $null = Get-Command winget -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# -- Step 1: Git -------------------------------------------------
Write-Host "Checking for Git..." -ForegroundColor Yellow

$GIT = $null
if (Get-Command git -ErrorAction SilentlyContinue) {
    $GIT = "git"
} else {
    # Check known install locations
    $knownPaths = @(
        "C:\Program Files\Git\cmd\git.exe",
        "C:\Program Files (x86)\Git\cmd\git.exe",
        "${env:LOCALAPPDATA}\Programs\Git\cmd\git.exe"
    )
    foreach ($p in $knownPaths) {
        if (Test-Path $p) {
            $GIT = $p
            break
        }
    }
}

if (-not $GIT) {
    Write-Host "Git not found. Installing..." -ForegroundColor Yellow
    if (Test-Winget) {
        winget install --id Git.Git --exact --silent --accept-package-agreements --accept-source-agreements
        Refresh-Path
        if (Get-Command git -ErrorAction SilentlyContinue) {
            $GIT = "git"
        } else {
            # Check known paths again after install
            foreach ($p in $knownPaths) {
                if (Test-Path $p) {
                    $GIT = $p
                    break
                }
            }
        }
    }
    if (-not $GIT) {
        Write-Host ""
        Write-Host "ERROR: Git is required but could not be installed automatically." -ForegroundColor Red
        Write-Host "Please install Git manually from: https://git-scm.com/download/win" -ForegroundColor Red
        Write-Host "Then re-run this installer."
        try { Stop-Transcript } catch { }
        exit 1
    }
}

Write-Host "Using Git: $(& $GIT --version)" -ForegroundColor Green
Write-Host ""

# -- Step 2: Python 3.12 -----------------------------------------
Write-Host "Checking for Python 3.12..." -ForegroundColor Yellow

$PYTHON = $null

# Try py launcher first (most reliable version selector on Windows)
try {
    $pyOutput = & py -3.12 --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        # Check it's not Microsoft Store Python (known venv issues)
        $pyPath = (& py -3.12 -c "import sys; print(sys.executable)" 2>&1)
        if ($pyPath -notmatch "WindowsApps") {
            $PYTHON = "py"
        } else {
            Write-Host "Skipping Microsoft Store Python (known venv issues)." -ForegroundColor Yellow
        }
    }
} catch { }

# Try python3.12 or python directly
if (-not $PYTHON) {
    foreach ($candidate in @("python3.12", "python")) {
        try {
            $ver = & $candidate --version 2>&1
            if ($ver -match "3\.12\." ) {
                $candidatePath = (& $candidate -c "import sys; print(sys.executable)" 2>&1)
                if ($candidatePath -notmatch "WindowsApps") {
                    $PYTHON = $candidate
                    break
                }
            }
        } catch { }
    }
}

if (-not $PYTHON) {
    Write-Host "Python 3.12 not found. Installing..." -ForegroundColor Yellow
    if (Test-Winget) {
        winget install --id Python.Python.3.12 --exact --silent --accept-package-agreements --accept-source-agreements
        Refresh-Path
        # Re-detect after install
        try {
            $pyOutput = & py -3.12 --version 2>&1
            if ($LASTEXITCODE -eq 0) {
                $PYTHON = "py"
            }
        } catch { }
        if (-not $PYTHON) {
            try {
                $ver = & python --version 2>&1
                if ($ver -match "3\.12\.") {
                    $PYTHON = "python"
                }
            } catch { }
        }
    }
    if (-not $PYTHON) {
        Write-Host ""
        Write-Host "ERROR: Python 3.12 is required but could not be installed automatically." -ForegroundColor Red
        Write-Host "Please install Python 3.12 from: https://www.python.org/downloads/" -ForegroundColor Red
        Write-Host "Make sure to check 'Add Python to PATH' during installation."
        Write-Host "Then re-run this installer."
        try { Stop-Transcript } catch { }
        exit 1
    }
}

# Resolve the actual python command for venv creation
if ($PYTHON -eq "py") {
    $PYTHON_ARGS = @("-3.12")
    $pyVersion = & py -3.12 --version 2>&1
} else {
    $PYTHON_ARGS = @()
    $pyVersion = & $PYTHON --version 2>&1
}

Write-Host "Using Python: $pyVersion" -ForegroundColor Green
Write-Host ""

# -- Step 3: Clone/update repo -----------------------------------
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null

if (Test-Path (Join-Path $REPO_DIR ".git")) {
    Write-Host "Updating FastLRSearch..." -ForegroundColor Yellow
    try {
        & $GIT -C $REPO_DIR pull --ff-only 2>&1 | Out-Null
    } catch {
        Write-Host "  (git pull skipped - may have local changes)" -ForegroundColor DarkYellow
    }
} else {
    Write-Host "Downloading FastLRSearch..." -ForegroundColor Yellow
    & $GIT clone $REPO_URL $REPO_DIR
}
Write-Host ""

# -- Step 4: Virtual environment ----------------------------------
Write-Host "Setting up virtual environment..." -ForegroundColor Yellow

$VENV_PYTHON = Join-Path $VENV_DIR "Scripts\python.exe"
$VENV_PIP = Join-Path $VENV_DIR "Scripts\pip.exe"
$needsRecreate = $false

if (Test-Path $VENV_PYTHON) {
    # Check Python version matches
    $venvVersion = & $VENV_PYTHON --version 2>&1
    if ($venvVersion -notmatch "3\.12\.") {
        Write-Host "  Existing venv uses wrong Python version ($venvVersion). Recreating..." -ForegroundColor Yellow
        $needsRecreate = $true
    }
}

if ($needsRecreate -or -not (Test-Path $VENV_PYTHON)) {
    if (Test-Path $VENV_DIR) {
        Remove-Item -Recurse -Force $VENV_DIR
    }
    & $PYTHON @PYTHON_ARGS -m venv $VENV_DIR
}

# Verify venv
$venvCheck = & $VENV_PYTHON -c "import sys; print(sys.executable)" 2>&1
Write-Host "  Venv Python: $venvCheck" -ForegroundColor DarkGray
Write-Host ""

# -- Step 5: PyTorch ----------------------------------------------
Write-Host "Checking for NVIDIA GPU..." -ForegroundColor Yellow

$hasNvidia = $false
try {
    $gpus = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match "NVIDIA" }
    if ($gpus) {
        $hasNvidia = $true
        Write-Host "  Found: $($gpus[0].Name)" -ForegroundColor Green
    }
} catch { }

$installCuda = $false
if ($hasNvidia) {
    Write-Host ""
    $response = Read-Host "NVIDIA GPU detected. Install CUDA version for faster performance? [Y/n]"
    if ($response -eq "" -or $response -match "^[Yy]") {
        $installCuda = $true
    }
}

Write-Host ""
# pip writes progress/warnings to stderr; PowerShell treats stderr as errors
# with $ErrorActionPreference=Stop, so temporarily switch to Continue for pip calls.
$savedEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"

if ($installCuda) {
    Write-Host "Installing PyTorch with CUDA support (this may take several minutes)..." -ForegroundColor Yellow
    & $VENV_PIP install torch torchvision --no-cache-dir --index-url https://download.pytorch.org/whl/cu121 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
} else {
    Write-Host "Installing PyTorch (CPU)..." -ForegroundColor Yellow
    & $VENV_PIP install torch torchvision --no-cache-dir 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
}
Write-Host ""

# -- Step 6: Install FastLRSearch ---------------------------------
Write-Host "Installing FastLRSearch (this may take a few minutes)..." -ForegroundColor Yellow
& $VENV_PIP install --upgrade pip --quiet 2>&1 | Out-Null
& $VENV_PIP install --no-cache-dir $REPO_DIR 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

$ErrorActionPreference = $savedEAP

# Health check
Write-Host "Verifying installation..." -ForegroundColor Yellow
$healthCheck = & $VENV_PYTHON -c "from fastlrsearch.main import main; print('ok')" 2>&1
if ($healthCheck -ne "ok") {
    Write-Host "WARNING: Health check returned unexpected output: $healthCheck" -ForegroundColor Red
    Write-Host "The installation may still work. Continuing..." -ForegroundColor Yellow
}
Write-Host ""

# -- Step 7: Launcher ---------------------------------------------
Write-Host "Setting up launcher..." -ForegroundColor Yellow

$launcherSrc = Join-Path $REPO_DIR "windows\launcher.pyw"
$launcherDest = Join-Path $INSTALL_DIR "launcher.pyw"
if (Test-Path $launcherSrc) {
    Copy-Item -Force $launcherSrc $launcherDest
} else {
    Write-Host "  WARNING: launcher.pyw not found in repo, skipping." -ForegroundColor Yellow
}

# -- Step 8: Start Menu shortcut ----------------------------------
Write-Host "Creating Start Menu shortcut..." -ForegroundColor Yellow

$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$shortcutPath = Join-Path $startMenuDir "$APP_NAME.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $VENV_DIR "Scripts\pythonw.exe"
$shortcut.Arguments = "`"$launcherDest`""
$shortcut.WorkingDirectory = $INSTALL_DIR

# Set icon if available
$icoPath = Join-Path $REPO_DIR "windows\FastLRSearch.ico"
if (Test-Path $icoPath) {
    $shortcut.IconLocation = "$icoPath,0"
}

$shortcut.Save()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($shortcut) | Out-Null
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($WshShell) | Out-Null

Write-Host "  Shortcut: $shortcutPath" -ForegroundColor DarkGray
Write-Host ""

# -- Step 9: CLI wrapper ------------------------------------------
Write-Host "Setting up CLI command..." -ForegroundColor Yellow

$cmdSrc = Join-Path $REPO_DIR "windows\fastlrsearch.cmd"
$cmdDest = Join-Path $INSTALL_DIR "fastlrsearch.cmd"
if (Test-Path $cmdSrc) {
    Copy-Item -Force $cmdSrc $cmdDest
} else {
    Write-Host "  WARNING: fastlrsearch.cmd not found in repo, skipping." -ForegroundColor Yellow
}

# Add to User PATH (never touch Machine PATH)
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }

$pathEntries = $userPath -split ";" | Where-Object { $_ -ne "" }
if ($INSTALL_DIR -notin $pathEntries) {
    $pathEntries += $INSTALL_DIR
    $newUserPath = ($pathEntries | Select-Object -Unique) -join ";"
    [System.Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    Write-Host "  Added $INSTALL_DIR to User PATH." -ForegroundColor DarkGray
    Write-Host "  NOTE: Open a new terminal to use the 'fastlrsearch' command." -ForegroundColor Yellow
} else {
    Write-Host "  Already on User PATH." -ForegroundColor DarkGray
}
Write-Host ""

# -- Step 10: Lightroom plugin (optional) -------------------------
$lrPluginSrc = Join-Path $REPO_DIR "fastlrsearch.lrplugin"
if (Test-Path $lrPluginSrc) {
    $response = Read-Host "Install Lightroom Classic plugin? [y/N]"
    if ($response -match "^[Yy]") {
        $lrModules = Join-Path $env:APPDATA "Adobe\Lightroom\Modules"
        New-Item -ItemType Directory -Force -Path $lrModules | Out-Null
        $lrDest = Join-Path $lrModules "fastlrsearch.lrplugin"
        if (Test-Path $lrDest) {
            Remove-Item -Recurse -Force $lrDest
        }
        Copy-Item -Recurse $lrPluginSrc $lrDest
        Write-Host "Lightroom plugin installed!" -ForegroundColor Green
        Write-Host ""
    }
}

# -- Done ---------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Launch:  Windows key -> type '$APP_NAME'"
Write-Host "   or:   Start Menu -> $APP_NAME"
Write-Host ""
Write-Host "CLI:     fastlrsearch  (open a NEW terminal first)"
Write-Host ""
Write-Host "First launch will download the AI model (~1.5 GB)."
Write-Host ""
Write-Host "To update later:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$REPO_DIR\windows\install.ps1`""
Write-Host ""
Write-Host "Log: $LOG_FILE"

try { Stop-Transcript } catch { }
