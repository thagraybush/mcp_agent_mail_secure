# CI guards

## ty-check-baseline.sh

No-regression type-check guard. Runs `ty` and compares diagnostics against a reviewed baseline.

- **Passes** when all diagnostics exist in `ci/ty-baseline.txt` (fixes reduce the set freely).
- **Fails** when any new diagnostic appears that is not in the baseline.

### Baseline metadata

| Field | Value |
|-------|-------|
| Count | 174 diagnostics |
| Base commit | `72108dd` (main) |
| Generated | 2026-07-19 |
| Owner | operator (cfollmer) |
| Format | `file:line:col error[code]` (sorted, .venv excluded) |

### Refresh protocol

After fixing type errors, regenerate and review:

```bash
ci/ty-check-baseline.sh --refresh
git diff ci/ty-baseline.txt   # review: only removals expected
git add ci/ty-baseline.txt
```

Never refresh to accept NEW diagnostics without operator review.

### Seeded-failure proof

A new type error (e.g., `return "not an int"` in a `-> int` function) produces output like:

```
FAIL: 1 new ty diagnostic(s) not in baseline

New diagnostics:
src/mcp_agent_mail/capability_rbac.py:2:27 error[invalid-return-type]

Baseline: 174 | Current: 175 | New: 1
```
