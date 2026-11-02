-- The scanner can observe these calls; it cannot prove the handler is secure.
-- Example only. CanUseShop must be maintained by the server.
local Players = game:GetService("Players")
local remote = game:GetService("ReplicatedStorage"):WaitForChild("RequestItem")
local allowedItems = { bandage = true, radio = true }
local lastRequest = {}
local limiter = {}

function limiter:allow(userId)
    local now = os.clock()
    if lastRequest[userId] and now - lastRequest[userId] < 1 then
        return false
    end
    lastRequest[userId] = now
    return true
end

remote.OnServerEvent:Connect(function(player, itemId)
    if not limiter:allow(player.UserId) then return end
    if typeof(itemId) ~= "string" or #itemId > 40 then return end
    if not allowedItems[itemId] then return end
    if player:GetAttribute("CanUseShop") ~= true then return end
    -- Add the game's inventory transaction here. This example grants nothing.
    print("Accepted request", player.UserId, itemId)
end)

Players.PlayerRemoving:Connect(function(player)
    lastRequest[player.UserId] = nil
end)
