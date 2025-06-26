-- === Hammerspoon Configuration ===
-- Window management and automation for macOS

-- === Configurable Hotkey for Always-on-Top ===
local modifiers = {"ctrl", "alt"}      
local key = "P"                         

-- === Always-on-Top Toggle Functionality ===
local borders = {}  -- Store borders per window

hs.hotkey.bind(modifiers, key, function()
  local win = hs.window.focusedWindow()
  if not win then return end

  local winId = win:id()
  local topLevel = hs.drawing.windowLevels.floating
  local normalLevel = hs.drawing.windowLevels.normal

  if not win._isAlwaysOnTop then
    -- Set window to always on top
    win:setLevel(topLevel)
    win._isAlwaysOnTop = true

    -- Add visual border indicator
    local frame = win:frame()
    local border = hs.drawing.rectangle(frame)
    border:setStrokeColor({red=1, green=0, blue=0, alpha=0.8})
    border:setStrokeWidth(4)
    border:setFill(false)
    border:show()
    
    -- Store border reference
    borders[winId] = border

    hs.alert.show("Always on Top: ON", 1)
  else
    -- Set window back to normal level
    win:setLevel(normalLevel)
    win._isAlwaysOnTop = false

    -- Remove visual border
    if borders[winId] then
      borders[winId]:delete()
      borders[winId] = nil
    end

    hs.alert.show("Always on Top: OFF", 1)
  end
end)

-- === Window Event Handling ===
-- Clean up borders when windows are closed
local windowFilter = hs.window.filter.new()
windowFilter:subscribe(hs.window.filter.windowDestroyed, function(window)
  local winId = window:id()
  if borders[winId] then
    borders[winId]:delete()
    borders[winId] = nil
  end
end)

-- Update border position when window is moved/resized
windowFilter:subscribe({hs.window.filter.windowMoved, hs.window.filter.windowResized}, function(window)
  local winId = window:id()
  if borders[winId] and window._isAlwaysOnTop then
    borders[winId]:setFrame(window:frame())
  end
end)

-- === Auto-reload Configuration ===
hs.pathwatcher.new(os.getenv("HOME") .. "/.hammerspoon/", function()
  hs.reload()
end):start()

hs.alert.show("Hammerspoon Config Loaded", 1)

-- === Additional Useful Shortcuts (Optional) ===
-- Uncomment and modify these as needed

-- Window positioning shortcuts
-- hs.hotkey.bind({"cmd", "alt"}, "Left", function()
--   local win = hs.window.focusedWindow()
--   if win then
--     local screen = win:screen():frame()
--     win:setFrame({x=screen.x, y=screen.y, w=screen.w/2, h=screen.h})
--   end
-- end)

-- hs.hotkey.bind({"cmd", "alt"}, "Right", function()
--   local win = hs.window.focusedWindow()
--   if win then
--     local screen = win:screen():frame()
--     win:setFrame({x=screen.x + screen.w/2, y=screen.y, w=screen.w/2, h=screen.h})
--   end
-- end) 