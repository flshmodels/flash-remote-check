-- Compile examples without executing their Roblox API calls.
local fs = require("@lune/fs")
local luau = require("@lune/luau")
for _, name in ipairs(fs.readDir("examples")) do
    if name:match("%.luau$") then
        luau.compile(fs.readFile("examples/" .. name))
        print("Compiled " .. name)
    end
end
