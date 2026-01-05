--[[
    FastLRSearch Plugin Info Provider
    Settings UI for Plugin Manager
]]

local LrView = import 'LrView'
local LrPrefs = import 'LrPrefs'
local LrTasks = import 'LrTasks'
local LrDialogs = import 'LrDialogs'
local LrHttp = import 'LrHttp'

local function sectionsForTopOfDialog(f, propertyTable)
    local prefs = LrPrefs.prefsForPlugin()

    -- Initialize defaults if not set
    if prefs.apiHost == nil then prefs.apiHost = "localhost" end
    if prefs.apiPort == nil then prefs.apiPort = 17831 end
    if prefs.apiToken == nil then prefs.apiToken = "" end
    if prefs.resultLimit == nil then prefs.resultLimit = 50 end
    if prefs.photoRoot == nil then prefs.photoRoot = "" end

    -- For status display (not saved)
    propertyTable.connectionStatus = "Not tested"

    return {
        {
            title = "FastLRSearch Settings",
            synopsis = "Configure connection to FastLRSearch server",

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "API Host:",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:edit_field {
                    value = LrView.bind { key = 'apiHost', bind_to_object = prefs },
                    width_in_chars = 20,
                    immediate = true,
                },
            },

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "API Port:",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:edit_field {
                    value = LrView.bind { key = 'apiPort', bind_to_object = prefs },
                    width_in_chars = 8,
                    immediate = true,
                },
            },

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "API Token:",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:edit_field {
                    value = LrView.bind { key = 'apiToken', bind_to_object = prefs },
                    width_in_chars = 40,
                    immediate = true,
                },
            },

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "Result Limit:",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:popup_menu {
                    value = LrView.bind { key = 'resultLimit', bind_to_object = prefs },
                    items = {
                        { title = "20", value = 20 },
                        { title = "50", value = 50 },
                        { title = "100", value = 100 },
                        { title = "200", value = 200 },
                    },
                },
            },

            f:separator { fill_horizontal = 1 },

            f:row {
                spacing = f:control_spacing(),
                f:static_text {
                    title = "Photo Root (optional):",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:edit_field {
                    value = LrView.bind { key = 'photoRoot', bind_to_object = prefs },
                    width_in_chars = 40,
                    immediate = true,
                },
            },

            f:row {
                f:static_text {
                    title = "Auto-detected from catalog folders. Only set this if auto-detection\n" ..
                            "fails or you need to override (e.g., network path differences).",
                    width_in_chars = 50,
                    height_in_lines = 2,
                },
            },

            f:separator { fill_horizontal = 1 },

            f:row {
                spacing = f:control_spacing(),
                f:push_button {
                    title = "Test Connection",
                    action = function()
                        LrTasks.startAsyncTask(function()
                            local host = prefs.apiHost or "localhost"
                            local port = prefs.apiPort or 17831
                            local url = string.format("http://%s:%s/health", host, port)

                            local response, headers = LrHttp.get(url, nil, 5)

                            if response and headers and headers.status == 200 then
                                LrDialogs.message("Connection Test", "Success! Connected to FastLRSearch server.", "info")
                            elseif headers then
                                LrDialogs.message("Connection Test", "Failed: HTTP " .. tostring(headers.status), "warning")
                            else
                                LrDialogs.message("Connection Test", "Failed: Cannot connect to server.\n\nCheck that FastLRSearch is running and\nthe host/port settings are correct.", "critical")
                            end
                        end)
                    end,
                },
            },

            f:row {
                f:static_text {
                    title = "Note: The API token is shown in the FastLRSearch app's\n" ..
                            "status bar. You can also find it in the discovery file:\n" ..
                            "Windows: %LOCALAPPDATA%\\fastlrsearch\\api.json",
                    width_in_chars = 50,
                    height_in_lines = 3,
                },
            },
        },
    }
end

return {
    sectionsForTopOfDialog = sectionsForTopOfDialog,
}
