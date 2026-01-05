# FastLRSearch Lightroom Plugin

A Lightroom Classic plugin for semantic photo search powered by FastLRSearch.

## Features

- **Text Search**: Find photos using natural language queries (e.g., "sunset on beach", "people laughing", "mountain landscape")
- **Find Similar**: Select a photo and find visually similar images (fast - uses pre-computed vectors)
- **Connection Status**: Both dialogs show server connection status before searching
- **Auto Collection**: Results are automatically added to a collection for easy access
- **Cross-Platform**: Works with FastLRSearch running on a different machine (e.g., Linux server)

## Requirements

- Adobe Lightroom Classic (version 6.0 or later)
- FastLRSearch application running (either locally or on a server)

## Installation

### 1. Locate the Plugin

The plugin folder is named `fastlrsearch.lrplugin`. Copy it to a permanent location on your computer, for example:

- **Windows**: `C:\Users\<YourName>\Documents\LightroomPlugins\`
- **Mac**: `~/Documents/LightroomPlugins/`

### 2. Add Plugin to Lightroom

1. Open Lightroom Classic
2. Go to **File > Plug-in Manager...**
3. Click the **Add** button
4. Navigate to and select the `fastlrsearch.lrplugin` folder
5. Click **Select Folder** (Windows) or **Add Plug-in** (Mac)

The plugin should now appear in the list with a green status indicator.

## Configuration

### 1. Start FastLRSearch

Make sure the FastLRSearch application is running before using the plugin.

### 2. Get the API Token

In the FastLRSearch application:
- Go to **Tools > Copy API Token**
- The token is copied to your clipboard

Alternatively, find the token in the discovery file:
- **Windows**: `%LOCALAPPDATA%\fastlrsearch\api.json`
- **Linux**: `~/.local/share/fastlrsearch/api.json`

### 3. Configure the Plugin

1. In Lightroom, go to **File > Plug-in Manager...**
2. Select **FastLRSearch** in the left panel
3. Configure the settings:

| Setting | Description | Default |
|---------|-------------|---------|
| **API Host** | Server address | `localhost` |
| **API Port** | Server port | `17831` |
| **API Token** | Authentication token (required) | — |
| **Result Limit** | Maximum results per search | `50` |
| **Photo Root** | Override auto-detected path (optional) | — |

4. Click **Test Connection** to verify the setup

### Connection Scenarios

#### Same Machine (Recommended)
If FastLRSearch and Lightroom are on the same computer:
- API Host: `localhost`
- API Port: `17831`
- Photo Root: Leave empty (auto-detected)

#### Remote Server
If FastLRSearch runs on a different machine (e.g., Linux server with GPU):
- API Host: Server's IP address (e.g., `192.168.1.100`)
- API Port: `17831`
- Photo Root: Usually auto-detected, but may need manual override if paths differ

> **Note**: When using a remote server, ensure the FastLRSearch API is bound to `0.0.0.0` (not `127.0.0.1`) by setting `FASTLRSEARCH_API_HOST=0.0.0.0` before starting the application.

## Usage

### Text Search

1. Go to **Library > Plug-in Extras > Search Photos...**
2. Enter your search query (e.g., "red car", "birthday party", "flowers")
3. Select the maximum number of results
4. Click **Search**

Results are added to a new collection under **FastLRSearch Results** in the Collections panel.

### Find Similar

1. Select a photo in your catalog
2. Go to **Library > Plug-in Extras > Find Similar to Selected**
3. Verify the connection status and selected photo in the confirmation dialog
4. Adjust result limit if needed and click **Find Similar**

Results are added to a collection named "Similar to: [filename]".

> **Note**: Find Similar is fast for indexed photos because it uses pre-computed vectors instead of re-embedding the image.

## Troubleshooting

### "FastLRSearch Not Configured"
Configure the API token in Plugin Manager (File > Plug-in Manager > FastLRSearch).

### "Cannot connect to server"
- Verify FastLRSearch is running
- Check the API Host and Port settings
- If using a remote server, ensure firewall allows connections on port 17831

### "No Matching Photos in Catalog"
The search found results, but those photos aren't imported into your Lightroom catalog. Make sure:
- Photos are imported into Lightroom (not just referenced)
- The Photo Root setting matches where Lightroom sees the photos

### Photos Not Found (Path Mismatch)
If the plugin finds results but can't match them to your catalog:
1. Check if the Photo Root auto-detection is working
2. Try setting Photo Root manually to match your Lightroom folder path
3. Ensure the folder structure matches between FastLRSearch and Lightroom

## Search Tips

FastLRSearch uses semantic search, so you can use natural language:

- **Objects**: "red car", "wooden table", "coffee cup"
- **Scenes**: "beach sunset", "mountain landscape", "city street at night"
- **People**: "people laughing", "portrait of woman", "group photo"
- **Activities**: "playing guitar", "cooking", "reading book"
- **Moods**: "peaceful", "dramatic sky", "cozy interior"

The search understands context and concepts, not just keywords.

## License

This plugin is part of the FastLRSearch project.
