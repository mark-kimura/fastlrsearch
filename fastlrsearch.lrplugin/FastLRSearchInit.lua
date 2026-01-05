--[[
    FastLRSearch Plugin Initialization
]]

local LrPrefs = import 'LrPrefs'
local LrLogger = import 'LrLogger'

-- Initialize logger
local logger = LrLogger('FastLRSearch')
logger:enable("logfile")

-- Initialize default preferences
local prefs = LrPrefs.prefsForPlugin()

if prefs.apiHost == nil then prefs.apiHost = "localhost" end
if prefs.apiPort == nil then prefs.apiPort = 17831 end
if prefs.apiToken == nil then prefs.apiToken = "" end
if prefs.resultLimit == nil then prefs.resultLimit = 50 end

logger:trace("FastLRSearch plugin initialized")
