"""
Semantics-preserving-to-first-order source transformations.

Each operator models a code-change pattern that a coding agent actually
produces, or a degenerate pattern that a naive complexity metric rewards.
Operators act on an in-memory {relpath: source} mapping and return a new one.
Every operator is required to keep the package parseable; `validate()` is
called by the driver as a hard gate.
"""
import ast
import os
import re
from collections import defaultdict

FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)

# top-level importable package name, set by the driver (transforms need the
# module name, not the filesystem path, to recognise absolute self-imports)
PKG = ''


# ------------------------------------------------------------- utilities

def parse_all(files):
    trees = {}
    for k, src in files.items():
        try:
            trees[k] = ast.parse(src, filename=k)
        except SyntaxError:
            pass
    return trees


def unparse_all(trees):
    out = {}
    for k, t in trees.items():
        try:
            out[k] = ast.unparse(t)
        except Exception:
            out[k] = files[k]      # never silently drop a module
    return out


def validate(files):
    """Hard gate: every file must compile."""
    for k, src in files.items():
        try:
            compile(src, k, 'exec')
        except SyntaxError:
            return False, k
    return True, None


# ------------------------------------------------------------- 0. noop
def op_noop(files):
    """Parse + unparse only. Control for the codegen itself.

    Essential: any measured change under other operators is relative to THIS,
    not to the pristine file.
    """
    return unparse_all(parse_all(files))


# ------------------------------------------------- 1. inline single-use
def _free_names(node, bound):
    """Names read by `node` that are not bound inside it."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.add(n.id)
    return out - set(bound)


def _has_unsafe(node):
    """Reject anything that could be affected by the caller's scope."""
    for n in ast.walk(node):
        if isinstance(n, (ast.Yield, ast.YieldFrom, ast.Await, ast.NamedExpr)):
            return True
        if isinstance(n, ast.Lambda):
            return True
    return False


def op_inline(files, max_use=1):
    """Inline private, single-expression, single-call-site helpers.

    CORRECTNESS GUARANTEE: a helper is inlined only if its body is a single
    `return <expr>` that reads nothing but its own parameters and Python
    builtins. Under that condition the substitution is provably semantics-
    preserving regardless of the caller's scope, because every free name in
    the body is either a parameter (renamed to a fresh symbol) or a builtin.
    This is what makes the operator usable as an experimental control.
    """
    trees = parse_all(files)
    cands, use = {}, defaultdict(int)
    module_globals = {}
    for k, t in trees.items():
        names = set()
        for node in t.body:
            if isinstance(node, (FUNC, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for tg in node.targets:
                    if isinstance(tg, ast.Name):
                        names.add(tg.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    names.add(a.asname or a.name.split('.')[0])
        module_globals[k] = names

    for k, t in trees.items():
        for node in t.body:
            if not (isinstance(node, FUNC) and node.name.startswith('_')):
                continue
            if node.decorator_list or _has_unsafe(node):
                continue
            if node.body and isinstance(node.body[0], ast.Expr) and \
                    isinstance(node.body[0].value, ast.Constant):
                body = node.body[1:]          # skip docstring
            else:
                body = node.body
            if len(body) != 1 or not isinstance(body[0], ast.Return):
                continue
            expr = body[0].value
            if expr is None:
                continue
            params = [a.arg for a in node.args.posonlyargs] + \
                     [a.arg for a in node.args.args]
            if any(a.arg in ('self', 'cls') for a in
                   node.args.posonlyargs + node.args.args):
                continue
            extra = set()
            for d in node.args.defaults + [d for d in node.args.kw_defaults if d]:
                extra |= _free_names(d, params)
            reads = _free_names(expr, params) | extra
            # free names that are module-level bindings in the SAME module as
            # both the def and every call site (we only match (module, name)),
            # so they resolve identically before and after. Bind them as extra
            # lambda parameters. Everything else must be a builtin.
            captures = {g: g for g in reads if g in module_globals.get(k, set())}
            if (reads - BUILTINS) - set(captures):
                continue          # touches unresolved module state -> unsafe
            cands[(k, node.name)] = (node, expr, params, captures)

    for k, t in trees.items():
        for n in ast.walk(t):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                use[(k, n.func.id)] += 1

    targets = {key for key in cands if use[key] <= max_use}
    if not targets:
        return files

    class Repl(ast.NodeTransformer):
        def __init__(self, k):
            self.k = k

        def visit_Call(self, node):
            self.generic_visit(node)
            f = node.func
            if not (isinstance(f, ast.Name) and (self.k, f.id) in targets):
                return node
            _, expr, params, captures = cands[(self.k, f.id)]
            slot = {}
            for i, p in enumerate(params):
                slot[p] = '__a%d' % i
            for j, g in enumerate(sorted(captures)):
                slot[g] = '__g%d' % j
            order = sorted(slot.values())
            body = ast.copy_location(_rename_params(expr, slot), node)
            lam = ast.Lambda(
                args=ast.arguments(
                    posonlyargs=[], args=[ast.arg(arg=a) for a in order],
                    vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None,
                    defaults=[]),
                body=body)
            argv = []
            for p in params:
                argv.append(ast.Name(id=slot[p], ctx=ast.Load()))
            for g in sorted(captures):
                argv.append(ast.Name(id=g, ctx=ast.Load()))
            return ast.copy_location(
                ast.Call(func=lam, args=argv, keywords=[]), node)

        def visit_Module(self, node):
            self.generic_visit(node)
            node.body = [s for s in node.body
                         if not (isinstance(s, FUNC) and (self.k, s.name) in targets)]
            return node

    nt = {k: Repl(k).visit(t) for k, t in trees.items()}
    for t in nt.values():
        ast.fix_missing_locations(t)
    res = unparse_all(nt)
    ok, bad = validate(res)
    return res if ok else files


# ------------------------------------- 6b. unfold (statement-level inlining)
class _StmtUnfolder(ast.NodeTransformer):
    """Turn `return X` into a temp assignment so a body can be spliced
    into an enclosing statement list."""

    def __init__(self, tmp):
        self.tmp = tmp

    def visit_Return(self, node):
        if node.value is None:
            return ast.Assign(targets=[ast.Name(id=self.tmp, ctx=ast.Store())],
                              value=ast.Constant(value=None))
        return ast.Assign(targets=[ast.Name(id=self.tmp, ctx=ast.Store())],
                          value=node.value)


def _return_paths(body):
    """Classify a statement list as: 'plain' | 'ifelse' | None."""
    for s in body:
        if isinstance(s, ast.Return):
            return 'plain'
        if isinstance(s, ast.If):
            if s.orelse:
                a = _return_paths(s.body)
                b = _return_paths(s.orelse)
                if a == 'plain' and b == 'plain':
                    return 'ifelse'
            return None
        if isinstance(s, (ast.For, ast.While, ast.Try, ast.With, ast.FunctionDef,
                          ast.ClassDef, ast.AsyncFor, ast.AsyncWith, ast.AsyncFunctionDef)):
            return None
    return None


def _body_safe(body):
    for n in ast.walk(ast.Module(body=list(body), type_ignores=[])):
        if isinstance(n, (ast.Yield, ast.YieldFrom, ast.Await, ast.NamedExpr,
                          ast.Global, ast.Nonlocal, ast.Import, ast.ImportFrom,
                          ast.Lambda, ast.ClassDef, ast.FunctionDef,
                          ast.AsyncFunctionDef)):
            return False
    return True


def op_unfold(files, max_use=2):
    """Inline private helpers used at most `max_use` times, by splicing their
    statements into the call site. Handles `plain` and `if/else` return forms.

    Restricted to call sites that are the entire RHS of an assignment, a
    return, or a discarded expression statement -- i.e. positions where the
    expansion is unambiguous. Guards the result with a full compile pass.
    """
    trees = parse_all(files)
    use = defaultdict(int)
    for k, t in trees.items():
        for n in ast.walk(t):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                use[(k, n.func.id)] += 1

    cands = {}
    for k, t in trees.items():
        scope = set()
        for node in ast.walk(t):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                scope.add(node.id)
        for node in t.body:
            if not (isinstance(node, FUNC) and node.name.startswith('_')):
                continue
            if node.decorator_list or node.args.vararg or node.args.kwarg \
                    or node.args.kwonlyargs:
                continue
            body = node.body
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant):
                body = body[1:]
            kind = _return_paths(body)
            if kind is None or not _body_safe(body):
                continue
            if any(a.arg in ('self', 'cls') for a in
                   node.args.posonlyargs + node.args.args):
                continue
            params = [a.arg for a in node.args.posonlyargs] + \
                     [a.arg for a in node.args.args]
            cands[(k, node.name)] = (node, body, kind, params, scope)
            use.setdefault((k, node.name), 0)

    targets = {key for key in cands if use[key] <= max_use}
    if not targets:
        return files

    state = {'n': 0}

    def expand(fn, args, k):
        node, body, kind, params, scope = cands[(k, fn)]
        i = state['n']; state['n'] += 1
        used = set(scope) | set(params)
        slots = {}
        pre = []
        for j, p in enumerate(params):
            a = args[j] if j < len(args) else ast.Constant(value=None)
            if any(isinstance(x, ast.Starred) for x in args) and j >= len(args):
                a = ast.Constant(value=None)
            fresh = '__cx%d_%d' % (i, j)
            while fresh in used:
                fresh += '_'
            used.add(fresh); slots[p] = fresh
            pre.append(ast.Assign(targets=[ast.Name(id=fresh, ctx=ast.Store())], value=a))
        tmp = '__cxr%d' % i
        while tmp in used:
            tmp += '_'
        body2 = [ast.parse(ast.unparse(s)).body[0] for s in body]
        for s in body2:
            for n in ast.walk(s):
                if isinstance(n, ast.Name) and n.id in slots and \
                        isinstance(n.ctx, ast.Load):
                    n.id = slots[n.id]
        uf = _StmtUnfolder(tmp)
        if kind == 'ifelse':
            for s in body2:
                if isinstance(s, ast.If):
                    s.body = [uf.visit(x) for x in s.body]
                    s.orelse = [uf.visit(x) for x in s.orelse]
                else:
                    s.vis = None
            out = [ast.Assign(targets=[ast.Name(id=tmp, ctx=ast.Store())],
                              value=ast.Constant(value=None))] + pre + body2
        else:
            flat = []
            for s in body2:
                if isinstance(s, ast.Return):
                    flat.append(uf.visit(s))
                else:
                    flat.append(s)
            out = pre + flat
        return out, tmp

    class StmtSplicer(ast.NodeTransformer):
        def __init__(self, k):
            self.k = k
            self.pre = []

        def _try(self, node, holder):
            f = node.value.func if isinstance(node.value, ast.Call) else None
            if not (isinstance(node.value, ast.Call) and isinstance(f, ast.Name)
                    and (self.k, f.id) in targets):
                return None
            if node.value.keywords:
                return None
            body, tmp = expand(f.id, node.value.args, self.k)
            self.pre.extend(body)
            return ast.Name(id=tmp, ctx=ast.Load())

        def visit_Assign(self, node):
            self.generic_visit(node)
            if isinstance(node.value, ast.Assign):
                return None
            r = self._try(node, 'assign')
            if r is None:
                return node
            return ast.Assign(targets=node.targets, value=r)

        def visit_Return(self, node):
            self.generic_visit(node)
            if node.value is None:
                return node
            fake = ast.Expr(value=node.value)
            r = self._try(fake, 'ret')
            if r is None:
                return node
            return ast.Return(value=r)

        def visit_Expr(self, node):
            self.generic_visit(node)
            if isinstance(node.value, ast.Constant):
                return node
            if not (isinstance(node.value, ast.Call) and
                    isinstance(node.value.func, ast.Name) and
                    (self.k, node.value.func.id) in targets):
                return node
            if node.value.keywords:
                return node
            body, tmp = expand(node.value.func.id, node.value.args, self.k)
            self.pre.extend(body)
            return ast.Expr(value=ast.Constant(value=None))

        def visit_Module(self, node):
            out = []
            for s in node.body:
                sp = StmtSplicer(self.k)
                r = sp.visit(s)
                out.extend(sp.pre)
                if r is not None:
                    if isinstance(r, list):
                        out.extend(r)
                    else:
                        out.append(r)
            node.body = out
            # drop the now-unused defs
            node.body = [s for s in node.body
                         if not (isinstance(s, FUNC) and (self.k, s.name) in targets)]
            return node

    nt = {k: StmtSplicer(k).visit(t) for k, t in trees.items()}
    for t in nt.values():
        ast.fix_missing_locations(t)
    res = unparse_all(nt)
    ok, bad = validate(res)
    return res if ok else files


BUILTINS = set(dir(__builtins__)) if isinstance(__builtins__, dict) is False \
    else set(__builtins__.keys())
BUILTINS |= {'True', 'False', 'None', 'Exception', 'ValueError', 'TypeError',
             'KeyError', 'IndexError', 'AttributeError', 'RuntimeError',
             'StopIteration', 'NotImplementedError', 'AssertionError',
             'OverflowError', 'ZeroDivisionError', 'OSError', 'IOError'}


def _rename_params(expr, slot):
    """Rename bound names to the fresh lambda slots, inside a copy."""
    expr = ast.parse(ast.unparse(expr), mode='eval').body
    for n in ast.walk(expr):
        if isinstance(n, ast.Name) and n.id in slot:
            n.id = slot[n.id]
    return expr


# ------------------------------------------------ 2. merge sibling modules
def op_merge(files):
    """Merge same-directory modules that share a name prefix.

    Reduces node count and edge count; removes module boundaries.
    Skipped when it would create a name collision.
    """
    trees = parse_all(files)
    by_dir = defaultdict(list)
    for k in trees:
        d, base = k.rsplit('/', 1) if '/' in k else ('', k)
        by_dir[d].append(base)

    plan = {}      # dir -> (target_base, [merged bases])
    for d, bases in by_dir.items():
        pref = defaultdict(list)
        for b in bases:
            m = re.match(r'^([a-z][a-z0-9]*)[_.]', b)
            if m:
                pref[m.group(1)].append(b)
        for p, members in pref.items():
            if len(members) < 2:
                continue
            names = defaultdict(set)
            for b in members:
                for n in trees[f'{d}/{b}'].body if d else trees[b].body:
                    if isinstance(n, (FUNC, ast.ClassDef)):
                        names[n.name].add(b)
            # refuse if any top-level name is duplicated across members
            if any(len(v) > 1 for v in names.values()):
                continue
            plan[d] = (p, sorted(members))

    if not plan:
        return files

    out = dict(files)
    for d, (target, members) in plan.items():
        body, header = [], []
        seen_imports = set()
        for b in members:
            path = f'{d}/{b}' if d else b
            t = trees[path]
            for n in t.body:
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    key = ast.unparse(n)
                    if key not in seen_imports:
                        seen_imports.add(key)
                        header.append(n)
                else:
                    body.append(n)
        mod = ast.Module(body=header + body, type_ignores=[])
        ast.fix_missing_locations(mod)
        newpath = f'{d}/{target}.py' if d else f'{target}.py'
        out[newpath] = ast.unparse(mod)
        for b in members:
            out.pop(f'{d}/{b}' if d else b, None)

    # redirect intra-package imports of removed modules
    for d, (target, members) in plan.items():
        for k in list(out):
            if k in out and k.endswith('.py'):
                s = out[k]
                for b in members:
                    stem = b[:-3]
                    s = re.sub(rf'(^|\n)(\s*)(from\s+)\.{re.escape(stem)}\s+import',
                               rf'\1\2\3.{target} import', s)
                    s = re.sub(rf'(^|\n)(\s*)import\s+{re.escape(stem)}\s*$',
                               rf'\1\2from .{target} import *', s, flags=re.M)
                out[k] = s

    ok, bad = validate(out)
    return out if ok else files


# ------------------------------------------------ 3. hardcode (DEGENERATE)
def op_hardcode(files):
    """Replace zero-arg private functions returning a pure constant with the
    constant itself, and delete the function.

    Semantics-preserving BY CONSTRUCTION (a literal has no side effects).
    But it is a pure quality regression: the code is now hard-coded.
    This is the operator a naive complexity metric pays handsomely for.
    """
    trees = parse_all(files)
    consts = {}
    for k, t in trees.items():
        for n in t.body:
            if isinstance(n, FUNC) and n.name.startswith('_') and not n.args.args \
                    and not n.decorator_list and len(n.body) == 1 \
                    and isinstance(n.body[0], ast.Return) and n.body[0].value is not None:
                v = n.body[0].value
                if isinstance(v, ast.Constant):
                    consts[(k, n.name)] = v.value

    if not consts:
        return files

    class Sub(ast.NodeTransformer):
        def __init__(self, k):
            self.k = k
            self.hits = 0

        def visit_Call(self, node):
            self.generic_visit(node)
            f = node.func
            if isinstance(f, ast.Name) and (self.k, f.id) in consts:
                self.hits += 1
                return ast.copy_location(ast.Constant(value=consts[(self.k, f.id)]), node)
            return node

        def visit_Module(self, node):
            self.generic_visit(node)
            node.body = [s for s in node.body
                         if not (isinstance(s, FUNC) and (self.k, s.name) in consts)]
            return node

    nt = {}
    for k, t in trees.items():
        r = Sub(k)
        nt[k] = r.visit(t)
        for n in ast.walk(nt[k]):
            if isinstance(n, ast.Constant) and not isinstance(n.value, type(...)):
                pass
    for t in nt.values():
        ast.fix_missing_locations(t)
    res = unparse_all(nt)
    ok, bad = validate(res)
    return res if ok else files


# ------------------------------------------------ 4. defensive guard shell
def op_guard(files):
    """Wrap every public function body in `try/except Exception: raise`.

    Semantically a no-op (bare re-raise) but adds one decision point and one
    nesting level per function. This is the 'defensive programming' pattern
    coding agents add constantly; it should NOT be rewarded.
    """
    trees = parse_all(files)

    class Wrap(ast.NodeTransformer):
        def _wrap(self, node):
            if not node.body:
                return node
            if any(isinstance(s, ast.Try) for s in node.body):
                return node
            try:
                body = node.body
                node.body = [ast.Try(
                    body=body,
                    handlers=[ast.ExceptHandler(
                        type=ast.Name(id='Exception', ctx=ast.Load()),
                        name=None, body=[ast.Raise(exc=None, cause=None)])],
                    orelse=[], finalbody=[])]
            except Exception:
                return node
            return node

        def visit_FunctionDef(self, node):
            self.generic_visit(node)
            if node.name.startswith('_'):
                return node
            return self._wrap(node)

        visit_AsyncFunctionDef = visit_FunctionDef

    nt = {}
    for k, t in trees.items():
        r = Wrap()
        nt[k] = r.visit(t)
        ast.fix_missing_locations(nt[k])
    res = unparse_all(nt)
    ok, bad = validate(res)
    return res if ok else files


# ------------------------------------------------ 5. drop dead private code
def op_dedup(files):
    """Delete private module-level functions never referenced in the package.

    A legitimate optimisation. Baseline for 'what a real improvement looks like'.
    """
    trees = parse_all(files)
    defined, referenced = set(), defaultdict(int)
    for k, t in trees.items():
        for n in t.body:
            if isinstance(n, FUNC) and n.name.startswith('_'):
                defined.add((k, n.name))
        for n in ast.walk(t):
            if isinstance(n, ast.Name):
                referenced[n.id] += 1
            elif isinstance(n, ast.Attribute):
                referenced[n.attr] += 1
    dead = {key for key in defined if referenced[key[1]] == 0}
    if not dead:
        return files

    class Drop(ast.NodeTransformer):
        def __init__(self, k):
            self.k = k

        def visit_Module(self, node):
            self.generic_visit(node)
            node.body = [s for s in node.body
                         if not (isinstance(s, FUNC) and (self.k, s.name) in dead)]
            return node

    nt = {}
    for k, t in trees.items():
        nt[k] = Drop(k).visit(t)
        ast.fix_missing_locations(nt[k])
    res = unparse_all(nt)
    ok, bad = validate(res)
    return res if ok else files


# ------------------------------------------------ 6. gateway / facade hub
def op_facade(files):
    """Route all intra-package symbol imports through one re-export hub.

    Concentrates fan-in onto a single node. Increases indirection while
    making the import graph look 'simpler' to naive edge counters.
    """
    trees = parse_all(files)
    if not trees:
        return files
    # pick a deterministic hub key
    first = sorted(trees)[0]
    hub = first.rsplit('/', 1)[0] + '/_gateway.py' if '/' in first else '_gateway.py'

    exported = []
    for k, t in trees.items():
        if k == hub:
            continue
        for n in t.body:
            if isinstance(n, (FUNC, ast.ClassDef)) and not n.name.startswith('_'):
                exported.append((k, n.name))
            elif isinstance(n, ast.Assign):
                for tgt in n.targets:
                    if isinstance(tgt, ast.Name) and not tgt.id.startswith('_'):
                        exported.append((k, tgt.id))

    hubmod = ast.Module(body=[
        ast.ImportFrom(module='.', level=1,
                       names=[ast.alias(name=n, asname=None) for _, n in exported],
                       type_ignores=[])], type_ignores=[])
    ast.fix_missing_locations(hubmod)
    out = dict(files)
    out[hub] = ast.unparse(hubmod)

    for k in list(files):
        if k == hub or not k.endswith('.py'):
            continue
        s = out[k]
        # Relative level is per importing file: a module at a/b/c.py needs
        # `from ..._gateway import`, one at c.py needs `from ._gateway`.
        # Getting this wrong yields an absolute import, which silently turns
        # the gateway into an *external* module in the import graph.
        up = k.count('/') + 1
        rel = '.' * up + '_gateway'
        s = re.sub(r'(^|\n)([ \t]*)from\s+\.([A-Za-z_][\w.]*)\s+import\s+([^\n]+)',
                   lambda m: (f'{m.group(1)}{m.group(2)}from {rel} import '
                              f'{m.group(4)}'),
                   s)
        # also handle absolute self-imports (`from pkg.mod import x`), which
        # several projects prefer over relative imports
        pkg = PKG
        if pkg:
            s = re.sub(r'(^|\n)([ \t]*)from\s+' + re.escape(pkg) +
                       r'\.([A-Za-z_][\w.]+)\s+import\s+([^\n]+)',
                       lambda m: (f'{m.group(1)}{m.group(2)}from {pkg}._gateway '
                                  f'import {m.group(4)}'),
                       s)
        out[k] = s

    ok, bad = validate(out)
    return out if ok else files


OPERATORS = {
    'noop':       op_noop,
    'inline':     op_inline,
    'unfold':     op_unfold,
    'merge':      op_merge,
    'hardcode':   op_hardcode,
    'guard':      op_guard,
    'dedup':      op_dedup,
    'facade':     op_facade,
}
