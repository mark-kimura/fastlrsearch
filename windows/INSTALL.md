# Installing FastLRSearch on Windows

## Prerequisites

- **Windows 10** (version 1709 or later) or **Windows 11**
- No administrator privileges required

## Install

Open PowerShell and paste:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/mark-kimura/fastlrsearch/master/windows/install.ps1 -OutFile $env:TEMP\fastlrsearch-install.ps1; & $env:TEMP\fastlrsearch-install.ps1"
```

This handles everything automatically:
- Installs Git and Python 3.12 (if needed, via winget)
- Installs PyTorch with CUDA support (if you have an NVIDIA GPU and choose yes)
- Installs FastLRSearch in a virtual environment
- Creates a Start Menu shortcut
- Optionally installs the Lightroom plugin

## After Install

- **Launch**: Windows key → type "FastLRSearch"
- **CLI**: Open a **new** terminal and type `fastlrsearch`
- First launch downloads the AI model (~1.5 GB one-time download)
- Set your photo root directory in Preferences (Ctrl+,)

## Update

```powershell
powershell -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\fastlrsearch\repo\windows\install.ps1"
```

## Lightroom Plugin

If you skipped it during install:

```powershell
fastlrsearch --install-lrplugin
```

Then in Lightroom:
- Make sure FastLRSearch desktop app is running
- **Library → Plug-in Extras → Search Photos...**
- **Library → Plug-in Extras → Find Similar to Selected**

## Uninstall

1. Delete the Start Menu shortcut:
   ```powershell
   Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\FastLRSearch.lnk"
   ```

2. Delete the install directory:
   ```powershell
   Remove-Item -Recurse "$env:LOCALAPPDATA\fastlrsearch"
   ```

3. Remove from PATH (optional):
   Open Settings → System → About → Advanced system settings → Environment Variables → edit User PATH → remove the `fastlrsearch` entry.

## Log Locations

| Log | Path |
|-----|------|
| Installer | `%LOCALAPPDATA%\fastlrsearch\logs\install.log` |
| Application | `%LOCALAPPDATA%\fastlrsearch\logs\FastLRSearch.log` |

## Troubleshooting

### "Running scripts is disabled on this system"

The install command already uses `-ExecutionPolicy Bypass`. If you still see this error, try running PowerShell as Administrator and executing:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "This file came from another computer and might be blocked"

If you downloaded the script manually, Windows may block it (Mark-of-the-Web). Unblock it:
```powershell
Unblock-File "$env:TEMP\fastlrsearch-install.ps1"
```

### Antivirus blocking the install

Some antivirus software may flag Python scripts or pip installs. Temporarily disable real-time scanning during install, or add `%LOCALAPPDATA%\fastlrsearch` to your antivirus exclusions.

### winget not available

On older Windows 10 builds, winget may not be installed. Install Git and Python 3.12 manually:
- Git: https://git-scm.com/download/win
- Python 3.12: https://www.python.org/downloads/ (check "Add Python to PATH")

Then re-run the installer.
