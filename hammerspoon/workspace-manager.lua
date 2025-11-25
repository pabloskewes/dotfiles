-- Modular workspace management system

local M = {}

-- ============================================
-- PROFILE CONFIGURATION
-- ============================================

M.profiles = {
  scopeo = {
    name = "Scopeo",
    
    iterm = {
      tabs = {
        { name = "Docker", command = "cd ~/Scopeo/draftnrun/services && docker compose up" },
        { name = "Frontend", command = "cd ~/Scopeo/back-office && npm run dev" },
        { name = "Backend", command = "cd ~/Scopeo/draftnrun && uv run python -m ada_backend.main" },
        { name = "Infra", command = "cd ~/Scopeo/ada-infra" },
        { name = "General", command = "cd ~/Scopeo/draftnrun" },
      },
      -- Auto-detect monitor: 1 = primary, 2 = secondary
      monitor = 1,
      -- Layout: if 1 monitor use "left", if 2 use "full"
      layout_single = { x = 0, y = 0, w = 0.5, h = 1 },
      layout_dual = { x = 0, y = 0, w = 1, h = 1 }
    },
    
    chrome = {
      urls = {
        "http://localhost:5173",
        "http://localhost:8080/admin",
        "https://localhost:8080/docs",
        "https://github.com/Scopeo/draftnrun/pulls",
      },
      monitor = 1,
      layout_single = { x = 0.5, y = 0, w = 0.5, h = 1 },
      layout_dual = { x = 0, y = 0, w = 1, h = 1 }
    },
    
    cursor = {
      workspace = "~/Scopeo/draftnrun",
      monitor = 2,
      layout_single = { x = 0, y = 0, w = 1, h = 1 },
      layout_dual = { x = 0, y = 0, w = 1, h = 1 }
    },
  },
  
  tesis = {
    name = "Tesis",
    
    iterm = {
      tabs = {
        { name = "General", command = "cd ~/FCFM/Magister/cltj" },
      },
      monitor = 1,
      layout_single = { x = 0, y = 0, w = 0.6, h = 1 },
      layout_dual = { x = 0, y = 0, w = 1, h = 1 }
    },
    
    chrome = {
      urls = {
        "https://github.com/pabloskewes/cltj",
      },
      monitor = 1,
      layout_single = { x = 0.6, y = 0, w = 0.4, h = 1 },
      layout_dual = { x = 0, y = 0, w = 1, h = 1 }
    },
    
    cursor = {
      workspace = "~/.cursor/tesis.code-workspace",
      monitor = 2,
      layout_single = { x = 0, y = 0, w = 1, h = 1 },
      layout_dual = { x = 0, y = 0, w = 1, h = 1 }
    },
  },
}

-- ============================================
-- STATE TRACKING
-- ============================================

M.activeProfiles = {}

-- ============================================
-- UTILITIES
-- ============================================

local function getScreenCount()
  return #hs.screen.allScreens()
end

local function getScreen(monitorNum)
  local screens = hs.screen.allScreens()
  local screenCount = #screens
  
  if screenCount == 1 then
    return screens[1]
  end
  
  if monitorNum > screenCount then
    return screens[1]
  end
  
  return screens[monitorNum]
end

local function positionWindow(win, config, monitorNum)
  local screenCount = getScreenCount()
  local screen = getScreen(monitorNum)
  local frame = screen:frame()
  
  local layout = (screenCount == 1) and config.layout_single or config.layout_dual
  
  win:setFrame({
    x = frame.x + (frame.w * layout.x),
    y = frame.y + (frame.h * layout.y),
    w = frame.w * layout.w,
    h = frame.h * layout.h
  })
end

local function generateWindowId(profileName, appName)
  return profileName .. "_" .. appName
end

-- ============================================
-- ITERM MANAGEMENT
-- ============================================

local function launchIterm(profileName, config)
  local script = [[
    tell application "iTerm"
      activate
      create window with default profile
      
      tell current session of current window
  ]]
  
  if config.tabs[1] then
    script = script .. string.format([[
        set name to "%s"
        write text "%s"
    ]], config.tabs[1].name, config.tabs[1].command)
  end
  
  for i = 2, #config.tabs do
    local tab = config.tabs[i]
    script = script .. string.format([[
      end tell
      tell current window
        create tab with default profile
      end tell
      tell current session of current window
        set name to "%s"
        write text "%s"
    ]], tab.name, tab.command)
  end
  
  script = script .. [[
      end tell
      
      return id of current window
    end tell
  ]]
  
  local success, windowId = hs.osascript.applescript(script)
  
  if success then
    hs.timer.doAfter(2, function()
      local iterm = hs.application.get("iTerm2")
      if iterm then
        local windows = iterm:allWindows()
        for _, win in ipairs(windows) do
          positionWindow(win, config, config.monitor)
          M.activeProfiles[generateWindowId(profileName, "iterm")] = {
            app = "iTerm2",
            windowId = windowId
          }
          break
        end
      end
    end)
  end
end

local function killIterm(profileName)
  local id = generateWindowId(profileName, "iterm")
  local tracked = M.activeProfiles[id]
  
  if not tracked then
    return
  end
  
  local script = string.format([[
    tell application "iTerm"
      repeat with w in windows
        if id of w is %s then
          close w
          return true
        end if
      end repeat
      return false
    end tell
  ]], tracked.windowId)
  
  pcall(hs.osascript.applescript, script)
  M.activeProfiles[id] = nil
end

-- ============================================
-- CHROME MANAGEMENT
-- ============================================

local function launchChrome(profileName, config)
  local chrome = hs.application.get("Google Chrome")
  
  if not chrome then
    hs.application.open("Google Chrome")
    hs.timer.doAfter(2, function()
      launchChrome(profileName, config)
    end)
    return
  end
  
  chrome:activate()
  
  local script = [[
    tell application "Google Chrome"
      make new window
      set windowId to id of front window
      return windowId
    end tell
  ]]
  
  local success, windowId = hs.osascript.applescript(script)
  
  if not success then return end
  
  for i, url in ipairs(config.urls) do
    local openScript
    if i == 1 then
      openScript = string.format([[
        tell application "Google Chrome"
          set URL of active tab of front window to "%s"
        end tell
      ]], url)
    else
      openScript = string.format([[
        tell application "Google Chrome"
          tell front window
            make new tab with properties {URL:"%s"}
          end tell
        end tell
      ]], url)
    end
    pcall(hs.osascript.applescript, openScript)
    hs.timer.usleep(300000)
  end
  
  hs.timer.doAfter(1, function()
    local windows = chrome:allWindows()
    if windows and #windows > 0 then
      positionWindow(windows[1], config, config.monitor)
      M.activeProfiles[generateWindowId(profileName, "chrome")] = {
        app = "Google Chrome",
        windowId = windowId
      }
    end
  end)
end

local function killChrome(profileName)
  local id = generateWindowId(profileName, "chrome")
  local tracked = M.activeProfiles[id]
  
  if not tracked then
    return
  end
  
  local script = string.format([[
    tell application "Google Chrome"
      repeat with w in windows
        if id of w is %s then
          close w
          return true
        end if
      end repeat
      return false
    end tell
  ]], tracked.windowId)
  
  pcall(hs.osascript.applescript, script)
  M.activeProfiles[id] = nil
end

-- ============================================
-- CURSOR MANAGEMENT
-- ============================================

local function launchCursor(profileName, config)
  local workspace = config.workspace:gsub("^~", os.getenv("HOME"))
  
  local cmd = string.format('open -a "Cursor" "%s"', workspace)
  hs.execute(cmd)
  
  hs.timer.doAfter(3, function()
    local cursor = hs.application.get("Cursor")
    if cursor then
      local win = cursor:mainWindow()
      if win then
        positionWindow(win, config, config.monitor)
        M.activeProfiles[generateWindowId(profileName, "cursor")] = {
          app = "Cursor",
          workspace = workspace
        }
      end
    end
  end)
end

local function killCursor(profileName)
  local id = generateWindowId(profileName, "cursor")
  local tracked = M.activeProfiles[id]
  
  if not tracked then
    return
  end
  
  local cursor = hs.application.get("Cursor")
  if cursor then
    local windows = cursor:allWindows()
    for _, win in ipairs(windows) do
      win:close()
    end
  end
  
  M.activeProfiles[id] = nil
end

-- ============================================
-- MAIN API
-- ============================================

function M.launch(profileName)
  local profile = M.profiles[profileName]
  
  if not profile then
    print("❌ Profile '" .. profileName .. "' does not exist")
    return false
  end
  
  local screenCount = getScreenCount()
  print(string.format("🖥️  Detected %d monitor(s)", screenCount))
  print("🚀 Launching: " .. profile.name)
  
  if profile.iterm then
    launchIterm(profileName, profile.iterm)
  end
  
  if profile.chrome then
    launchChrome(profileName, profile.chrome)
  end
  
  if profile.cursor then
    launchCursor(profileName, profile.cursor)
  end
  
  print("✅ Profile launched")
  return true
end

function M.kill(profileName)
  local profile = M.profiles[profileName]
  
  if not profile then
    print("❌ Profile '" .. profileName .. "' does not exist")
    return false
  end
  
  print("🛑 Closing: " .. profile.name)
  
  if profile.iterm then
    killIterm(profileName)
  end
  
  if profile.chrome then
    killChrome(profileName)
  end
  
  if profile.cursor then
    killCursor(profileName)
  end
  
  print("✅ Profile closed")
  return true
end

function M.list()
  print("\n📋 Available profiles:")
  for name, profile in pairs(M.profiles) do
    print(string.format("  • %s: %s", name, profile.name))
  end
  print("")
end

function M.status()
  print("\n🔍 Active workspaces:")
  local hasActive = false
  for id, info in pairs(M.activeProfiles) do
    print(string.format("  • %s (%s)", id, info.app))
    hasActive = true
  end
  if not hasActive then
    print("  (none)")
  end
  print("")
end

return M