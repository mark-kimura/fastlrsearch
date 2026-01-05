--[[
    FastLRSearch - Find Similar Menu Handler
    Finds photos similar to the selected photo and creates a collection with results
]]

local LrApplication = import 'LrApplication'
local LrDialogs = import 'LrDialogs'
local LrFunctionContext = import 'LrFunctionContext'
local LrTasks = import 'LrTasks'
local LrPrefs = import 'LrPrefs'
local LrProgressScope = import 'LrProgressScope'
local LrLogger = import 'LrLogger'

local FastLRSearchAPI = require 'FastLRSearchAPI'

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

-- Extract relative path from absolute path using photo root
local function extractRelativePath(absolutePath, photoRoot)
    if not photoRoot or photoRoot == "" then
        return nil
    end

    -- Normalize both paths to use forward slashes for comparison
    local normAbsolute = absolutePath:gsub("\\", "/")
    local normRoot = photoRoot:gsub("\\", "/"):gsub("/$", "") .. "/"

    -- Check if absolute path starts with photo root
    if normAbsolute:sub(1, #normRoot):lower() == normRoot:lower() then
        return normAbsolute:sub(#normRoot + 1)
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
local function findPhotosInCatalog(catalog, results, skipPath)
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

        -- Skip the source photo itself
        if searchPath and searchPath ~= skipPath then
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

-- Main find similar function
local function doFindSimilar()
    LrFunctionContext.postAsyncTaskWithContext("FastLRSearch Find Similar", function(context)
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

        -- Get the primary selected photo (the "most selected" one)
        local targetPhoto = catalog:getTargetPhoto()
        if not targetPhoto then
            LrDialogs.message(
                "No Photo Selected",
                "Please select a photo to find similar images.",
                "warning"
            )
            return
        end

        local targetPath = targetPhoto:getRawMetadata('path')

        if not targetPath then
            LrDialogs.message(
                "Cannot Get Photo Path",
                "Unable to get the file path for the selected photo.",
                "critical"
            )
            return
        end

        -- Get filename for display
        local filename = targetPath:match("([^/\\]+)$") or targetPath

        -- Extract relative path for cross-platform compatibility
        local photoRoot = detectPhotoRoot(catalog)
        local relativePath = extractRelativePath(targetPath, photoRoot)

        if not relativePath then
            LrDialogs.message(
                "Cannot Determine Relative Path",
                string.format(
                    "Could not extract relative path from:\n%s\n\nPhoto root: %s\n\n" ..
                    "Please configure Photo Root in Plugin Manager to match your Lightroom folder structure.",
                    targetPath, photoRoot or "(not detected)"
                ),
                "critical"
            )
            return
        end

        -- Perform search
        local progress = LrProgressScope {
            title = string.format("Finding photos similar to %s...", filename),
            functionContext = context,
        }
        progress:setCancelable(false)

        local limit = prefs.resultLimit or 50
        local searchResult, err = FastLRSearchAPI.findSimilar(relativePath, limit)

        if err then
            progress:done()
            LrDialogs.message("Search Error", "Failed to find similar photos: " .. err, "critical")
            return
        end

        if not searchResult or not searchResult.results or #searchResult.results == 0 then
            progress:done()
            LrDialogs.message("No Results", "No similar photos found.", "info")
            return
        end

        progress:setCaption("Processing results...")

        -- Find photos in catalog (skipping the source photo)
        local photos, notFound = findPhotosInCatalog(catalog, searchResult.results, targetPath)
        local totalResults = #searchResult.results - 1  -- Exclude source photo

        if #photos == 0 and #notFound == 0 then
            progress:done()
            LrDialogs.message("No Results", "No similar photos found (other than the source).", "info")
            return
        end

        if #photos == 0 then
            progress:done()
            LrDialogs.message(
                "No Matching Photos in Catalog",
                string.format(
                    "Found %d similar photos, but none are in this Lightroom catalog.\n" ..
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
        local collectionName = string.format("Similar to: %s (%d)", filename, #photos)
        local collection = createResultsCollection(catalog, collectionSet, collectionName, photos)

        progress:done()

        -- Report results
        local message
        if #notFound > 0 then
            message = string.format(
                "Found %d similar photos (of %d results).\n" ..
                "%d photos were not found in the catalog.\n\n" ..
                "Collection created: %s",
                #photos, totalResults, #notFound, collectionName
            )
        else
            message = string.format(
                "Found %d similar photos.\n\nCollection created: %s",
                #photos, collectionName
            )
        end

        LrDialogs.message("Find Similar Complete", message, "info")

        -- Select the collection in the library
        if collection then
            catalog:setActiveSources({ collection })
        end
    end)
end

-- Execute
doFindSimilar()
