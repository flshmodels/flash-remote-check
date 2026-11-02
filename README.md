# Flash Remote Check

A local review tool for Roblox remote handlers. Point it at your scripts to get a list of inbound callbacks and places to check for validation, throttling or forwarded client data.

It reads `.lua` and `.luau` files without executing or uploading them. It needs Python 3.11+ and no extra packages.

## Run

Extract the repository and open a terminal in its folder:

```sh
python flash_remote_check.py path/to/game/src
python flash_remote_check.py path/to/Shop.server.luau --format json
python flash_remote_check.py path/to/game/src --format sarif > remote-review.sarif
```

Use a Rojo source directory or scripts you exported yourself. Place files such as `.rbxl` are not supported, and the tool does not connect to Studio.

To try it first:

```sh
python flash_remote_check.py examples/review-me.server.luau
```

That example is deliberately unchecked and returns exit 1. **Do not install it in a game.** The other example, `observed-checks.server.luau`, shows calls the scanner can recognize and returns review notes.

## Checks

| Rule | What to inspect |
| --- | --- |
| RMC000 | A file or scope could not be processed. |
| RMC001 | Payload validation and game permissions. |
| RMC002 | Per-player throttling. |
| RMC003 | Payload names in `FireAllClients` arguments. |
| RMC004 | Payload names in `require` arguments. |
| RMC005 | Named callbacks, aliases or other unresolved inbound references. |

Inline `OnServerEvent` and `OnServerInvoke` callbacks are supported. Comments and ordinary strings are ignored. Named callbacks and wrappers are listed for manual inspection.

The default rate-helper names are `limiter.allow`, `limiter.tryAcquire`, `rateLimiter.allow` and `rateLimiter.tryAcquire`. Add another exact name with:

```sh
python flash_remote_check.py src --rate-helper RequestBudget.take
```

Both `RequestBudget.take(...)` and `RequestBudget:take(...)` match that option.

## Reading a report

Text reports use `file:line:column`. JSON adds the callback inventory and observed calls. SARIF output is available for compatible tools.

| Exit | Meaning |
| --- | --- |
| 0 | No warning-level hints; review notes may remain. |
| 1 | Review hints found. |
| 2 | Incomplete scan or usage error. |

**No warnings does not mean the code is safe.** This scanner matches tokens; it does not follow values, resolve names across scopes or inspect helper implementations. A matching check or limiter name does not establish that it works or runs before a side effect.

If-expressions and interpolated backtick strings are outside the supported subset and produce an incomplete scan. Escaped/dynamic property names and remote frameworks can be missed. Use Studio or `luau-analyze` for syntax and type checking.

See [rule examples](docs/RULES.md), [formats and scan limits](docs/REFERENCE.md), [testing](docs/TESTING.md), and [related tools](docs/RESEARCH.md).

## Development

```sh
python -m unittest discover -s tests -v
```

The lexer, analyzer and CLI live in `remote_check/`. CI runs tests on Windows/Linux and compiles the Luau examples without executing them.

MIT licensed. See [LICENSE](LICENSE).
