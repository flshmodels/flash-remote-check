# Reading a review hint

## Unchecked payload

```lua
remote.OnServerEvent:Connect(function(player, amount)
    player.leaderstats.Coins.Value += amount
end)
```

RMC001 asks for a validation review and RMC002 asks for a throttling review. The scanner does not calculate the effect on currency or know which game actions the player is allowed to request. A real implementation should use a server-owned price/reward and check player state.

## A helper can hide a real check

```lua
remote.OnServerEvent:Connect(function(player, item)
    if not Catalog.canBuy(player, item) then return end
    Inventory.buy(player, item)
end)
```

The validation helper's implementation is not followed, so RMC001 remains a warning. That warning is an instruction to inspect Catalog.canBuy, not a claim that validation is missing. A custom rate-helper option only records a named call; it does not suppress the general review notes.

## Seeing a check is not proof

```lua
remote.OnServerEvent:Connect(function(player, moduleId)
    require(moduleId)
    assert(type(moduleId) == "number")
end)
```

RMC004 reports the payload name in require. The type call is recorded too, but it occurs after the side effect and does not restrict the module to a server-owned allowlist. This tool has no control-flow model and does not certify the ordering.

## Bindings the scanner cannot resolve

```lua
remote.OnServerEvent:Connect(handleRequest)
local inbound = remote.OnServerEvent
remote.OnServerInvoke = wrappers.checked(handleRequest)
```

Each visible inbound API reference gets RMC005. An alias can later be used without the API name appearing again; that later binding cannot be discovered by this version. Search your framework's registration calls and inspect helper modules separately.

## Broadcasts and aliases

RMC003/RMC004 match payload name tokens inside call arguments. They are not taint analysis. `FireAllClients(payload.position)` is a hint, while `local alias = payload; FireAllClients(alias)` is not followed. A value that has already been validated can still produce a hint. A nested shadow or expression can also make a spelling match misleading. Never use these hints as automatic ban decisions or a security approval gate.
