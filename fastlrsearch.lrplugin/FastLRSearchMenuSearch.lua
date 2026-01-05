--[[
    FastLRSearch - Text Search Menu Handler
    Searches photos by text query and creates a collection with results
]]

local LrApplication = import 'LrApplication'
local LrDialogs = import 'LrDialogs'
local LrFunctionContext = import 'LrFunctionContext'
local LrBinding = import 'LrBinding'
local LrView = import 'LrView'
local LrTasks = import 'LrTasks'
local LrPrefs = import 'LrPrefs'
local LrProgressScope = import 'LrProgressScope'
local LrLogger = import 'LrLogger'

local FastLRSearchAPI = require 'FastLRSearchAPI'

-- LrColor may not be available in all LR versions
local LrColor
pcall(function() LrColor = import 'LrColor' end)

local logger = LrLogger('FastLRSearch')
logger:enable("logfile")

-- Create or get the FastLRSearch collection set
local function getOrCreateCollectionSet(catalog)
    local collectionSets = catalog:getChildCollectionSets()
    for _, cs in ipairs(collectionSets) do
        if cs:getName() == "FastLRSearch Results" then
            return cs
        end
    end

    -- Create new collection set
    local collectionSet
    catalog:withWriteAccessDo("Create FastLRSearch collection set", function()
        collectionSet = catalog:createCollectionSet("FastLRSearch Results", nil, true)
    end)
    return collectionSet
end

-- Create a collection with search results
local function createResultsCollection(catalog, collectionSet, name, photos)
    local collection
    catalog:withWriteAccessDo("Create search results collection", function()
        -- Remove existing collection with same name
        local existingCollections = collectionSet:getChildCollections()
        for _, c in ipairs(existingCollections) do
            if c:getName() == name then
                c:delete()
                break
            end
        end
        collection = catalog:createCollection(name, collectionSet, true)
    end)

    if collection and #photos > 0 then
        catalog:withWriteAccessDo("Add photos to collection", function()
            collection:addPhotos(photos)
        end)
    end

    return collection
end

-- Detect photo root from catalog's folder structure
local function detectPhotoRoot(catalog)
    local prefs = LrPrefs.prefsForPlugin()

    -- Use manual override if set
    if prefs.photoRoot and prefs.photoRoot ~= "" then
        return prefs.photoRoot
    end

    -- Try to get root folders from catalog
    local folders = catalog:getFolders()
    if folders and #folders > 0 then
        -- Get the path of the first root folder
        local firstFolder = folders[1]
        local folderPath = firstFolder:getPath()
        if folderPath then
            return folderPath
        end
    end

    return nil
end

-- Build absolute path from relative path using detected or configured photo root
local function buildAbsolutePath(relativePath, photoRoot)
    if not photoRoot or photoRoot == "" then
        return nil
    end

    -- Normalize photoRoot (ensure trailing separator)
    local sep = "\\"
    if not photoRoot:match("\\") then
        sep = "/"
    end
    photoRoot = photoRoot:gsub("[/\\]$", "") .. sep

    -- Convert forward slashes in relative path to match photoRoot style
    if sep == "\\" then
        relativePath = relativePath:gsub("/", "\\")
    else
        relativePath = relativePath:gsub("\\", "/")
    end

    return photoRoot .. relativePath
end

-- Find photos in catalog by their paths
local function findPhotosInCatalog(catalog, results)
    local photos = {}
    local notFound = {}

    -- Detect or get configured photo root
    local photoRoot = detectPhotoRoot(catalog)

    for _, item in ipairs(results) do
        local searchPath
        if photoRoot and item.path then
            -- Use relative path + detected/configured photoRoot
            searchPath = buildAbsolutePath(item.path, photoRoot)
        else
            -- Fall back to absolute_path from server
            searchPath = item.absolute_path
        end

        if searchPath then
            local photo = catalog:findPhotoByPath(searchPath)
            if photo then
                table.insert(photos, photo)
            else
                table.insert(notFound, searchPath)
            end
        end
    end

    return photos, notFound
end

-- Main search function
local function doSearch()
    LrFunctionContext.postAsyncTaskWithContext("FastLRSearch", function(context)
        local prefs = LrPrefs.prefsForPlugin()
        local catalog = LrApplication.activeCatalog()

        -- Check if token is configured
        if not prefs.apiToken or prefs.apiToken == "" then
            LrDialogs.message(
                "FastLRSearch Not Configured",
                "Please configure the API token in Plugin Manager (File > Plug-in Manager > FastLRSearch).",
                "warning"
            )
            return
        end

        -- Create dialog
        local f = LrView.osFactory()
        local props = LrBinding.makePropertyTable(context)
        props.searchQuery = ""
        props.resultLimit = prefs.resultLimit or 50

        local contents = f:column {
            spacing = f:dialog_spacing(),
            bind_to_object = props,

            f:row {
                f:static_text {
                    title = "Search for:",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:edit_field {
                    value = LrView.bind 'searchQuery',
                    width_in_chars = 40,
                    immediate = true,
                },
            },

            f:row {
                f:static_text {
                    title = "Max results:",
                    alignment = "right",
                    width = LrView.share "label_width",
                },
                f:popup_menu {
                    value = LrView.bind 'resultLimit',
                    items = {
                        { title = "20", value = 20 },
                        { title = "50", value = 50 },
                        { title = "100", value = 100 },
                        { title = "200", value = 200 },
                    },
                },
            },

            f:static_text {
                title = "Examples: 'sunset on beach', 'people laughing', 'mountain landscape'",
            },
        }

        local result = LrDialogs.presentModalDialog {
            title = "FastLRSearch - Semantic Search",
            contents = contents,
            actionVerb = "Search",
        }

        if result ~= "ok" then
            return
        end

        local query = props.searchQuery
        if not query or query == "" then
            LrDialogs.message("Search Error", "Please enter a search query.", "warning")
            return
        end

        -- Perform search
        local progress = LrProgressScope {
            title = "Searching...",
            functionContext = context,
        }
        progress:setCancelable(false)

        local searchResult, err = FastLRSearchAPI.search(query, props.resultLimit)

        if err then
            progress:done()
            LrDialogs.message("Search Error", "Failed to search: " .. err, "critical")
            return
        end

        if not searchResult or not searchResult.results or #searchResult.results == 0 then
            progress:done()
            LrDialogs.message("No Results", "No photos found matching: " .. query, "info")
            return
        end

        progress:setCaption("Processing results...")

        -- Find photos in catalog
        local photos, notFound = findPhotosInCatalog(catalog, searchResult.results)
        local totalResults = #searchResult.results

        if #photos == 0 then
            progress:done()
            LrDialogs.message(
                "No Matching Photos in Catalog",
                string.format(
                    "Found %d results, but none are in this Lightroom catalog.\n" ..
                    "Make sure the photos are imported into Lightroom.",
                    totalResults
                ),
                "warning"
            )
            return
        end

        progress:setCaption("Creating collection...")

        -- Create collection with results
        local collectionSet = getOrCreateCollectionSet(catalog)
        local collectionName = string.format("Search: %s (%d)", query, #photos)
        local collection = createResultsCollection(catalog, collectionSet, collectionName, photos)

        progress:done()

        -- Report results
        local message
        if #notFound > 0 then
            message = string.format(
                "Found %d photos (of %d results).\n" ..
                "%d photos were not found in the catalog.\n\n" ..
                "Collection created: %s",
                #photos, totalResults, #notFound, collectionName
            )
        else
            message = string.format(
                "Found %d photos.\n\nCollection created: %s",
                #photos, collectionName
            )
        end

        LrDialogs.message("Search Complete", message, "info")

        -- Select the collection in the library
        if collection then
            catalog:setActiveSources({ collection })
        end
    end)
end

-- Execute
doSearch()
