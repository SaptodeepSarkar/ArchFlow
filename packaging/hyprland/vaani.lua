-- Vaani voice dictation binds for Lua-driven Hyprland setups.
-- Paste into your keybinds file (uses the global `hl` from the plugin).
-- Set VAANI_BIN to your install: ~/.local/bin/vaani (install.sh) or
-- /usr/bin/vaani (package).
local VAANI_BIN = os.getenv("HOME") .. "/.local/bin/vaani"
hl.bind("SUPER + H", hl.dsp.exec_cmd(VAANI_BIN .. " live-toggle"))
hl.bind("SUPER + ALT + SPACE", hl.dsp.exec_cmd(VAANI_BIN .. " toggle"))
hl.bind("SUPER + ALT + ESCAPE", hl.dsp.exec_cmd(VAANI_BIN .. " cancel"))
hl.bind("SUPER + ALT + S", hl.dsp.exec_cmd(VAANI_BIN .. " settings"))
hl.bind("SUPER + ALT + C", hl.dsp.exec_cmd(VAANI_BIN .. " copy"))
