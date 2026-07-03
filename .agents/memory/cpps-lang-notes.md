---
name: CP+* interpreter project notes
description: Durable lessons from building/fixing the CP+* custom language interpreter (cpps-lang/)
---

## Project location
Standalone Python CLI project at `cpps-lang/` (workspace root), unrelated to the
web artifacts (api-server, mockup-sandbox). Deliverable is a zip via
`present_asset`, not a deployed artifact.

## Debugging lesson: dead AST node classes
The parser defined `LambdaExpr` (dataclass) and even had a working
`visit_LambdaExpr` in the interpreter, but `parser.py` never actually
constructed a `LambdaExpr(...)` anywhere — the primary-expression parser
had no lookahead logic to recognize `(params) -> Type ** { body }` as a
lambda, so it silently parsed the leading `(...)` as a tuple/paren
expression instead, and closures returned `none`.

**Why this matters:** grepping for a class *definition* or its *visitor/eval
method* is not enough evidence that a grammar rule is implemented. Always
grep for `ClassName(` (constructor call sites) to confirm something in the
parser actually produces that node. A fully-implemented-looking evaluator
can be dead code if nothing ever creates the node it handles.

**Fix pattern used:** added a speculative/backtracking helper
(`_try_parse_lambda`) invoked at the start of the `LPAREN` branch in
`parse_primary`. It saves `self.pos`, tries to parse a param list + `)` +
`->` + return type + optional `**` + block/expr body, and restores position
on any mismatch/ParseError so normal tuple/paren parsing still works when
the lookahead isn't a lambda.

## Debugging lesson: `expect()` swallows errors, backtracking must restore them too
`Parser.expect()` never raises — on mismatch it appends to `self.errors` and
returns `None`, then callers (e.g. `parse_param_list`) keep going with
placeholder values instead of aborting. This broke `_try_parse_lambda`'s
backtracking: it only restored `self.pos` on failure, not `self.errors`, so
a failed speculative lambda attempt (triggered by any `(` at statement/
expression start) left phantom "N parse errors" behind even though the
position rollback made the actual parse succeed via the fallback path.
**Fix pattern:** any speculative/backtracking parse in this codebase must
snapshot `len(self.errors)` alongside `self.pos`, and on any bail-out path
`del self.errors[errors_start:]` in addition to restoring `self.pos`.

## Debugging lesson: statement-level `IDENT ::` dispatch ambiguity
`parse_stmt` used a fixed 2-token lookahead (`IDENT` then `DOUBLE_COLON`) to
decide "this is a variable declaration" and unconditionally called
`parse_var_decl()`. But `DOUBLE_COLON` after an identifier is *also* how
namespaced/static calls look (`fs::mkdir(...)`, `io::println(...)`,
`crypto::sha256(...)`). Because `parse_var_decl` has a legacy fallback that
tries to parse a value even without `=`, it silently swallowed the call's
`(args)` as an implicit tuple initializer — the call never actually
happened (e.g. `fs::mkdir(...)` parsed as `VarDecl(name="fs", type="mkdir",
value=(args tuple))`, and no directory was ever created), with no error
reported at all since parsing "succeeded".
**Fix pattern:** added `_looks_like_var_decl()`, a pure-lookahead helper
(no token consumption) that walks the `IDENT (:: IDENT)*` chain after the
leading `::` and checks what follows it: if immediately followed by `(`,
treat it as a namespaced call expression, not a var decl. `:: mut` is
still unconditionally a var decl. This class of bug (two grammar
constructs sharing a token prefix) is likely to recur — when adding new
`::`-based syntax, check this disambiguation still holds.

## Correct CP+* syntax notes
- Method calls use single colon: `obj:method(args)` (COLON), not `::`.
- `::` (DOUBLE_COLON) is namespace/static access: `ClassName::new(args)`,
  `std::io::println`.
- Lambda/closure literal syntax: `(params) -> ReturnType ** { body }`
  (the `**` before the block is optional in the grammar but commonly used).
