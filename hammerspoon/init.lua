-- Enable IPC for CLI access
require("hs.ipc")

-- Load workspace manager
workspaceManager = require("workspace-manager")

-- Load notification
hs.alert.show("Workspace Manager loaded! 🚀")
workspaceManager.list()