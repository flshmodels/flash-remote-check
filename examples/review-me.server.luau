-- Deliberately unchecked example for the scanner. Do not install in a game.
local remote = game:GetService("ReplicatedStorage"):WaitForChild("GiveCoins")
remote.OnServerEvent:Connect(function(player, amount)
    player.leaderstats.Coins.Value += amount
    remote:FireAllClients(amount)
end)
