--[[
    FastLRSearch API Module
    HTTP client for communicating with the FastLRSearch server
]]

local LrHttp = import 'LrHttp'
local LrPrefs = import 'LrPrefs'
local LrErrors = import 'LrErrors'

local JSON = require 'JSON'

local FastLRSearchAPI = {}

-- Get preferences
local function getPrefs()
    return LrPrefs.prefsForPlugin()
end

-- Get API base URL
function FastLRSearchAPI.getBaseUrl()
    local prefs = getPrefs()
    local host = prefs.apiHost or "localhost"
    local port = prefs.apiPort or 17831
    return string.format("http://%s:%d", host, port)
end

-- Get API token
function FastLRSearchAPI.getToken()
    local prefs = getPrefs()
    return prefs.apiToken or ""
end

-- Make authenticated GET request
function FastLRSearchAPI.get(endpoint, params)
    local baseUrl = FastLRSearchAPI.getBaseUrl()
    local token = FastLRSearchAPI.getToken()

    -- Build URL with query params
    local url = baseUrl .. endpoint
    if params then
        local queryParts = {}
        for key, value in pairs(params) do
            -- URL encode the value
            local encoded = string.gsub(tostring(value), "([^%w%-_.~])", function(c)
                return string.format("%%%02X", string.byte(c))
            end)
            table.insert(queryParts, key .. "=" .. encoded)
        end
        if #queryParts > 0 then
            url = url .. "?" .. table.concat(queryParts, "&")
        end
    end

    -- Headers
    local headers = {
        { field = "X-App-Token", value = token },
        { field = "Accept", value = "application/json" },
    }

    -- Make request
    local response, responseHeaders = LrHttp.get(url, headers, 30)

    if not response then
        return nil, "Network error: could not connect to server"
    end

    local status = responseHeaders and responseHeaders.status
    if status ~= 200 then
        return nil, string.format("HTTP error %d", status or 0)
    end

    -- Parse JSON response
    local success, result = pcall(function()
        return JSON:decode(response)
    end)

    if not success then
        return nil, "Invalid JSON response"
    end

    return result, nil
end

-- Health check
function FastLRSearchAPI.healthCheck()
    local baseUrl = FastLRSearchAPI.getBaseUrl()
    local url = baseUrl .. "/health"

    local response, responseHeaders = LrHttp.get(url, nil, 5)

    if not response then
        return false, "Cannot connect to server"
    end

    local status = responseHeaders and responseHeaders.status
    if status ~= 200 then
        return false, string.format("Server returned status %d", status or 0)
    end

    return true, "Connected"
end

-- Text search
function FastLRSearchAPI.search(query, limit)
    limit = limit or 50
    return FastLRSearchAPI.get("/search", {
        q = query,
        limit = limit,
    })
end

-- Find similar by file path
function FastLRSearchAPI.findSimilar(filePath, limit)
    limit = limit or 50
    return FastLRSearchAPI.get("/search/similar", {
        path = filePath,
        limit = limit,
    })
end

return FastLRSearchAPI
