# Research notes

Reviewed November 2, 2026. These comparisons are based on public documentation, not a benchmark or an audit of the other tools. Their code was not copied into this project.

| Reference | What informed this project |
| --- | --- |
| [RoScanner](https://github.com/alexandervonarx/RoScanner) | Its README describes broader security/data-integrity rules, declaration resolution and place-file input. Flash Remote Check deliberately has a smaller token-based scope and lists unresolved bindings. |
| [Roblox Remote Security Analyzer](https://github.com/MythicalBeam/roblox-remote-security-analyzer) | Its README advertises remote validation checks and risk scores. Flash Remote Check emits review hints without a score or a safe/unsafe verdict. The repository page exposed documentation and a hosted demo; this comparison does not claim its implementation was tested. |
| [Luau](https://github.com/luau-lang/luau) | luau-analyze is the separate type-checking/linting tool. Flash Remote Check does not replace its parser, type system or lint checks. |
| [Selene](https://github.com/Kampfkarren/selene) | Its emphasis on reliable diagnostics informed the explicit evidence and limitations. This tool still has false positives and negatives because it does not resolve names or values. |
| [Roblox client/server security guidance](https://create.roblox.com/docs/scripting/security/client-server-boundary) | Review types, bounds, permission/context and per-player limits at the server boundary. A matching helper name is insufficient evidence that these checks work. |
| [Roblox remote events and callbacks](https://create.roblox.com/docs/scripting/events/remote) | The first inbound callback argument is supplied by Roblox and identifies the player. Later arguments are client payload candidates. |

The implementation is independent and uses the Python standard library. No existing analyzer was installed or run on this computer for the comparison.
