# Checks and remaining limits

Run `python -m unittest discover -s tests -v` from the repository root.

The suite covers inactive strings/comments, escaped quotes, long brackets, CRLF positions, typed callbacks, nested/adjacent handlers, named/wrapped references, varargs, broadcasts, dynamic require, helper-name matching, unsupported syntax, incomplete reports, limits, input preservation, JSON/SARIF, URI escaping and both CLI entrypoints. A fixed-seed malformed-input corpus checks that parser failures stay within SourceError rather than leaking implementation exceptions.

File tests cover invalid UTF-8, BOMs, uppercase extensions, missing paths, empty directories, simulated I/O failures and directory exclusions. A symlink test skips when the OS denies link creation; the Linux CI jobs exercise that path without changing Windows privileges.

CI runs Python 3.11 and 3.13 on Windows and Linux. Another job uses Lune to compile the two example scripts without running their Roblox API calls. Lune is installed only on that runner, not by the scanner.

These tests do not establish vulnerability detection accuracy on arbitrary games. This version has no independently labelled precision/recall dataset, cross-file resolution, Luau grammar coverage or live Studio integration. Its deliberately unchecked example must never be installed as gameplay code.

An additional smoke check found the inbound callback in the portfolio's anti-cheat example. Scanning the CAD bridge source returned an incomplete scan because nine files contain if-expressions or interpolated strings outside this version's subset. That result is intentional: those files need manual review, not a claim that they contain no remote problems.
