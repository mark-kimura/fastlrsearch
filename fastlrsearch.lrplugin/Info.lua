--[[
    FastLRSearch Lightroom Plugin
    Semantic photo search integration for Lightroom Classic
]]

return {
    LrSdkVersion = 10.0,
    LrSdkMinimumVersion = 6.0,

    LrToolkitIdentifier = "com.fastlrsearch.lightroom",
    LrPluginName = "FastLRSearch",

    LrPluginInfoUrl = "https://github.com/mark-kimura/fastlrsearch",

    -- Plugin initialization
    LrInitPlugin = "FastLRSearchInit.lua",

    -- Library menu items
    LrLibraryMenuItems = {
        {
            title = "Search Photos...",
            file = "FastLRSearchMenuSearch.lua",
        },
        {
            title = "Find Similar to Selected",
            file = "FastLRSearchMenuSimilar.lua",
        },
    },

    -- Plugin info provider (settings in Plugin Manager)
    LrPluginInfoProvider = "FastLRSearchInfoProvider.lua",

    VERSION = { major = 0, minor = 1, revision = 0, build = 1 },
}
