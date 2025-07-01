-- Toggle "Always on Top" using yabai: Float + Topmost
hs.hotkey.bind({"ctrl", "alt"}, "P", function()
  hs.task.new("/bin/zsh", nil, function() return true end, {
      "-c", "yabai -m window --toggle float; yabai -m window --toggle topmost"
  }):start()
  hs.alert.show("Toggled float + topmost")
end)
