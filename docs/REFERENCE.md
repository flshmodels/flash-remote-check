# Formats and scan limits

## Supported bindings

The scanner recognizes `.OnServerEvent:Connect(function(...) ... end)`, `Once`, `ConnectParallel`, and `.OnServerInvoke = function(...) ... end`. Ordinary quoted bracket properties are also recognized. It assumes the first named argument is Roblox's player argument; later arguments and varargs are payload candidates. It does not infer the receiver's class, so an unrelated object with the same API names can be reported.

Comments, quoted strings and long-bracket strings are excluded from matching. Nested function bodies do not supply validation evidence for their enclosing handler. Named callbacks, aliases and wrappers are listed for manual review rather than silently marked as checked.

Default helper names: `limiter.allow`, `limiter.tryAcquire`, `rateLimiter.allow`, `rateLimiter.tryAcquire`. Add your own exact dotted name:

```sh
python flash_remote_check.py src --rate-helper RequestBudget.take
```

This recognizes `RequestBudget.take(...)` and `RequestBudget:take(...)`. A matching name only records evidence; it does not prove that the call rejects spam or uses the right player. The option adds to the defaults, does not load a module, and can be repeated up to 32 times.

## Reports

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
