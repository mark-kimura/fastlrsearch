# Installing FastLRSearch on macOS

## One-Line Install

Open Terminal and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/mark-kimura/fastlrsearch/master/macos/install.sh | bash
```

This handles everything automatically:
- Installs Homebrew (if you don't have it)
- Installs Python (if needed)
- Installs FastLRSearch
- Creates the app in your Applications folder
- Optionally installs the Lightroom plugin

## After Install

- **Launch**: Cmd+Space → type "FastLRSearch"
- **Pin to Dock**: drag from Applications folder
- First launch downloads the AI model (~1.5 GB one-time download)
- Set your photo root directory in Preferences (Cmd+,)

## Update

```bash
~/.local/share/fastlrsearch/repo/macos/install.sh
```

## Lightroom Plugin

If you skipped it during install:

```bash
~/.local/share/fastlrsearch/repo/macos/install_lrplugin.sh
```

Then in Lightroom:
- Make sure FastLRSearch desktop app is running
- **Library → Plug-in Extras → Search Photos...**
- **Library → Plug-in Extras → Find Similar to Selected**

## Uninstall

```bash
rm -rf /Applications/FastLRSearch.app
rm -rf ~/.local/share/fastlrsearch
```
