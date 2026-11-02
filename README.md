# Flash Remote Check

Find inbound remote handlers in local Roblox scripts and make a review list. Each hint includes a file, line and column. The tool reads source files; it does not run a game, execute Luau or upload code.

This is a small token-based scanner, not a security verdict. It cannot prove that validation or rate limiting works. A report with no warnings does **not** mean the code is safe.

## Run it

Python 3.11+; no packages to install. Extract the repository, open a terminal in that folder, and run:

```sh
python flash_remote_check.py path/to/game/src
python flash_remote_check.py path/to/Shop.server.luau --format json
python flash_remote_check.py path/to/game/src --format sarif > remote-review.sarif
```

`python -m remote_check` is the same entrypoint. Scan the source directory from a Rojo project or scripts you exported yourself. This version does not read `.rbxl`, `.rbxlx` or `.rbxmx` files and does not connect to Studio.

Try the included examples:

```sh
python flash_remote_check.py examples/review-me.server.luau
python flash_remote_check.py examples/observed-checks.server.luau
```

The first is deliberately unchecked and returns exit 1. **Do not install it in a game.** The second contains observable checks and returns exit 0 with review notes. Neither example is a complete shop or economy system.

## What gets reported

| Rule | Review hint |
| --- | --- |
| RMC000 | A file or scope could not be fully processed. |
| RMC001 | Review payload validation. Reports whether a direct type/typeof/assert call mentions a payload name. |
| RMC002 | Review throttling. Reports whether a configured helper name appears in a call. |
| RMC003 | A payload name appears in FireAllClients arguments. |
| RMC004 | A payload name appears in require arguments. |
| RMC005 | An inbound API reference could not be inspected as an inline callback. |

The scanner recognizes `.OnServerEvent:Connect(function(...) ... end)`, `Once`, `ConnectParallel`, and `.OnServerInvoke = function(...) ... end`. Ordinary quoted bracket properties are also recognized. It assumes the first named argument is Roblox's player argument; later arguments and varargs are payload candidates. It does not infer the receiver's class, so an unrelated object with the same API names can be reported.

Comments, quoted strings and long-bracket strings are excluded from matching. Nested function bodies do not supply validation evidence for their enclosing handler. Named callbacks, aliases and wrappers are listed for manual review rather than silently marked as checked.

Default helper names: `limiter.allow`, `limiter.tryAcquire`, `rateLimiter.allow`, `rateLimiter.tryAcquire`. Add your own exact dotted name:

```sh
python flash_remote_check.py src --rate-helper RequestBudget.take
```

This recognizes `RequestBudget.take(...)` and `RequestBudget:take(...)`. A matching name only records evidence; it does not prove that the call rejects spam or uses the right player. The option adds to the defaults, does not load a module, and can be repeated up to 32 times.

## Reading the result

Text output uses `file:line:column`, suitable for editor terminal links. JSON includes the handler inventory, observed calls, hints, errors, skipped paths and counts. SARIF 2.1.0 includes the same diagnostics for compatible tools. Coordinates are one-based Unicode code-point columns. Paths are relative to the input directory, or the parent of a single input file. Reports include no source excerpts or credentials.

Exit codes: **0** means no warning-level review hints, **1** means review hints, and **2** means an incomplete scan or usage error. Analysis errors take priority over hints. Review notes do not fail the command. Unsupported bindings produce RMC005 warnings even if all files were lexically processed; `scanComplete` means file processing completed, not that all behavior was understood.

Output goes to stdout. Redirect it yourself to save a report; choose a destination outside the source files you are scanning. Python's help and usage errors go to stderr. Source inputs are never rewritten. There is no automatic storage, server, login, telemetry or network client.

## Limits

- No value tracking, cross-file analysis, scope/name resolution, control-flow analysis or type inference. A shadowed name can create misleading evidence. An alias or helper can hide a problem or a real check.
- Type annotations do not validate remote data at runtime. Even an observed runtime type check does not establish finite numbers, bounds, permissions, distance or safe ordering. Checks after a side effect are still listed as observed.
- This lexer supports a subset of Luau. If-expressions, ambiguous inline if forms and interpolated backtick strings produce RMC000 and exit 2 for that file. Generic inline callbacks and wrapped bindings need manual review. Other syntax may be tokenized without being valid Luau; use `luau-analyze` or Studio for syntax and type checking.
- Escaped/dynamic property names, indirect API access, remote frameworks, code generated at runtime, ProximityPrompts and ClickDetectors are outside the matching rules.
- Each file: 1 MiB, 100000 tokens, nesting 256 and 2000 inbound references. Each scan: 1000 source files, 32 MiB read, 20000 filesystem entries and 10000 retained hints plus a limit error. These bounds are not a runtime or memory guarantee.
- Child links/reparse points are skipped; an explicit linked input is rejected. Excluded directories: `.git`, `.venv`, `venv`, `node_modules`, `build`, `dist`, `__pycache__`. Skips are listed. This does not enforce an OS sandbox or defend against another process replacing files during a scan.

Always review the reported callback and its helpers yourself. See [rules and examples](docs/RULES.md), [research notes](docs/RESEARCH.md), and [testing](docs/TESTING.md).

## Development

```sh
python -m unittest discover -s tests -v
```

`remote_check/lexer.py` handles lexical tokens and block pairing. `analyzer.py` builds the inventory and hints. `cli.py` handles bounded file discovery and reports. They use Python's standard library only. CI tests Python on Windows/Linux and compiles the two Luau examples without executing them.

MIT licensed. See [LICENSE](LICENSE).
