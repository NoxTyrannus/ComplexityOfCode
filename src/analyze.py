"""
Three-axis structural complexity analyzer.

Axis S (Structure)  : topology of the module dependency graph
Axis C (Coupling)   : cross-boundary interface exposure
Axis L (Node logic) : intra-procedural decision complexity (McCabe)

Design constraint: the three axes must NOT be linear functions of one another,
otherwise no trade-off is observable. Each is computed from a different
syntactic level (import statements / module interface / statement flow).
"""
import ast
import os
import hashlib
from collections import defaultdict


# ---------------------------------------------------------------- file scan

def repo_files(root):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in
                  {'.git', '__pycache__', 'test', 'tests', 'docs', 'benchmarks',
                   'build', 'dist', '.tox', 'node_modules', 'vendor'}]
        for f in fn:
            if f.endswith('.py'):
                out.append(os.path.join(dp, f))
    return sorted(out)


SKIP_DIRS = {'test', 'tests', 'docs', 'benchmarks', 'build', 'dist', '.tox',
             'node_modules', 'vendor', 'examples', 'example', 'tools', 'bin',
             'scripts', 'bench', 'ext', 'lib', 'src', 'debian', 'scripts/ci'}


def top_package(root):
    """Top-level importable package directory inside repo."""
    # 1) explicit override for known layouts
    for d in os.listdir(root):
        p = os.path.join(root, d)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, '__init__.py')):
            if d in ('anyio', 'click', 'flask', 'jsonschema', 'pytest',
                     'requests', 'sphinx', 'tox', 'urllib3', 'werkzeug',
                     'fastapi', 'black'):
                return d

    cands = [d for d in os.listdir(root)
             if os.path.isdir(os.path.join(root, d)) and not d.startswith(('.', '_'))
             and d not in SKIP_DIRS]
    if cands:
        # prefer a dir with __init__.py, else the largest
        dirs = [c for c in cands if os.path.exists(os.path.join(root, c, '__init__.py'))]
        if dirs:
            return max(dirs, key=lambda d: len(repo_files(os.path.join(root, d))))
        # src/ layout: look inside
        for c in ('src', 'lib'):
            sub = os.path.join(root, c)
            if os.path.isdir(sub):
                inner = [d for d in os.listdir(sub)
                         if os.path.isdir(os.path.join(sub, d))
                         and os.path.exists(os.path.join(sub, d, '__init__.py'))
                         and not d.startswith(('_', '.'))]
                if inner:
                    return os.path.join(c, max(inner))
        return max(cands, key=lambda d: len(repo_files(os.path.join(root, d))))

    files = [f for f in os.listdir(root) if f.endswith('.py')
             and f not in ('setup.py', 'conftest.py', 'noxfile.py')]
    return files[0][:-3] if len(files) == 1 else None


# ---------------------------------------------------------------- axis L

class ComplexityVisitor(ast.NodeVisitor):
    """McCabe cyclomatic complexity + decision-point census."""

    def __init__(self):
        self.cc = 1
        self.decisions = 0
        self.branches = defaultdict(int)
        self.depth = 0
        self.max_depth = 0

    def _dec(self, n=1):
        self.cc += n
        self.decisions += n

    def _nest(self, n=1):
        self.depth += n
        self.max_depth = max(self.max_depth, self.depth)

    def visit_If(self, n):
        self._dec(); self._nest(); self.branches['if'] += 1
        for f in n.body: self.visit(f)
        for f in n.orelse:
            if len(n.orelse) == 1 and isinstance(n.orelse[0], ast.If):
                self.visit(n.orelse[0])
            else:
                self._nest(-1); self.visit(f); self._nest(1)
        self._nest(-1)

    def visit_For(self, n):
        self._dec(); self._nest(); self.branches['for'] += 1
        self.visit(n.iter)
        for f in n.body: self.visit(f)
        for f in n.orelse: self.visit(f)
        self._nest(-1)

    visit_AsyncFor = visit_For

    def visit_While(self, n):
        self._dec(); self._nest(); self.branches['while'] += 1
        self.visit(n.test)
        for f in n.body: self.visit(f)
        for f in n.orelse: self.visit(f)
        self._nest(-1)

    def visit_IfExp(self, n):
        self._dec(); self.branches['ternary'] += 1; self.generic_visit(n)

    def visit_BoolOp(self, n):
        self._dec(len(n.values) - 1); self.branches['boolop'] += len(n.values) - 1
        self.generic_visit(n)

    def visit_ExceptHandler(self, n):
        self._dec(); self._nest(); self.branches['except'] += 1
        for f in n.body: self.visit(f)
        self._nest(-1)
        if isinstance(n.type, (ast.expr,)):     # `except SomeError as e:` binds a Name
            self.visit(n.type)

    def visit_comprehension(self, n):
        self._dec(1 + len(n.ifs)); self.branches['comprehension'] += 1
        self.generic_visit(n)

    def visit_Assert(self, n):
        self._dec(); self.branches['assert'] += 1; self.generic_visit(n)

    def visit_Match(self, n):
        self._dec(); self._nest(); self.branches['match'] += 1
        for c in n.cases: self.visit(c)
        self._nest(-1)

    def visit_With(self, n):
        self._nest(); self.branches['with'] += 1
        for i in n.items: self.visit(i.context_expr)
        for f in n.body: self.visit(f)
        self._nest(-1)

    visit_AsyncWith = visit_With

    def visit_Try(self, n):
        self._nest()
        for f in n.body: self.visit(f)
        for h in n.handlers: self.visit(h)
        for f in n.orelse: self.visit(f)
        for f in n.finalbody: self.visit(f)
        self._nest(-1)


class ExprNestVisitor(ast.NodeVisitor):
    """Expression nesting depth + boolean-operator density.

    McCabe counts *decisions*; it is blind to a single 40-token chained
    expression with no branch in it. This measures that other axis: how deep
    the expression trees inside a single statement go.
    """

    def __init__(self):
        self.max_depth = 0
        self.boolops = 0
        self.calls = 0
        self.stmts = 0
        self._d = 0

    def _nest(self, n, body):
        self._d += n
        self.max_depth = max(self.max_depth, self._d)
        for b in body:
            self.visit(b)
        self._d -= n

    def visit_Expr(self, n):
        self.stmts += 1
        self.visit(n.value)

    def visit_Return(self, n):
        self.stmts += 1
        if n.value:
            self.visit(n.value)

    def visit_Assign(self, n):
        self.stmts += 1
        self.visit(n.value)

    def visit_AugAssign(self, n):
        self.stmts += 1
        self.visit(n.value)

    def visit_Call(self, n):
        self.calls += 1
        self._nest(1, [n.func] + list(n.args) + [k.value for k in n.keywords])

    def visit_BoolOp(self, n):
        self.boolops += len(n.values) - 1
        self._nest(1, n.values)

    def visit_BinOp(self, n):
        self._nest(1, [n.left, n.right])

    def visit_UnaryOp(self, n):
        self._nest(1, [n.operand])

    def visit_Compare(self, n):
        self._nest(1, list(n.comparators))

    def visit_IfExp(self, n):
        self._nest(1, [n.test, n.body, n.orelse])

    def visit_Subscript(self, n):
        self._nest(1, [n.value, n.slice])

    def visit_Attribute(self, n):
        self._nest(1, [n.value])


    def visit_Slice(self, n):
        self._nest(1, [x for x in (n.lower, n.upper, n.step) if x is not None])

    def visit_JoinedStr(self, n):
        self._nest(1, list(n.values))

    def visit_ListComp(self, n):
        self._nest(1, [n.elt] + list(n.generators))

    visit_SetComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, n):
        self._nest(1, [n.key, n.value] + list(n.generators))

    def visit_comprehension(self, n):
        self._nest(1, [n.iter] + list(n.ifs))

    def visit_Await(self, n):
        self._nest(1, [n.value])

    def visit_If(self, n):
        self._nest(1, list(n.body) + list(n.orelse) + [n.test])

    def visit_For(self, n):
        self._nest(1, list(n.body) + list(n.orelse) + [n.iter])

    visit_AsyncFor = visit_For

    def visit_While(self, n):
        self._nest(1, list(n.body) + list(n.orelse) + [n.test])

    def visit_Try(self, n):
        self._nest(1, list(n.body) + list(n.orelse) + list(n.finalbody) +
                   [h for x in n.handlers for h in x.body])

    def visit_Assign_in_withitem(self, n):
        self.generic_visit(n)


def proc_stats(node):
    v = ComplexityVisitor()
    for st in node.body:
        v.visit(st)
    return v


def expr_stats(tree):
    v = ExprNestVisitor()
    v.visit(tree)
    return v


# ---------------------------------------------------------------- axis S

class ImportCollector(ast.NodeVisitor):
    """Collect intra-package import edges from a module."""

    def __init__(self, modname, pkg):
        self.mod = modname
        self.pkg = pkg
        self.edges = set()      # resolved module names
        self.ext_edges = set()  # external (out-of-package) top-level modules

    def _add(self, target):
        if target == self.mod:
            return
        if target.startswith(self.pkg):
            self.edges.add(target)
        else:
            self.ext_edges.add(target.split('.')[0])

    def visit_Import(self, n):
        for a in n.names:
            self._add(a.name)

    def visit_ImportFrom(self, n):
        base = n.module or ''
        if n.level and n.level > 0:
            # relative: walk up from self.mod
            parts = self.mod.split('.')[:-1]
            up = n.level - 1
            if up:
                parts = parts[:-up] if up <= len(parts) else []
            if n.module:
                parts = parts + n.module.split('.')
            self._add('.'.join(parts))
            for a in n.names:
                sub = '.'.join(parts + [a.name]) if parts else a.name
                self._add(sub)
        else:
            if base:
                self._add(base)
                for a in n.names:
                    self._add(base + '.' + a.name)

    def visit_Call(self, n):
        # `from x import y` done lazily, plus importlib usage
        f = n.func
        if isinstance(f, ast.Attribute):
            v = f.value
            if isinstance(v, ast.Name) and v.id == 'importlib' and f.attr == 'import_module':
                if n.args and isinstance(n.args[0], ast.Constant) and \
                        isinstance(n.args[0].value, str):
                    self._add(n.args[0].value)
        self.generic_visit(n)


# ---------------------------------------------------------------- core

EFFECTIVE = None


def _effective_lines(src_lines, tree):
    """SLOC excluding blanks, comments, docstrings."""
    doc_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            d = ast.get_docstring(node, clean=False)
            if d is not None:
                b = node.body[0]
                doc_lines.update(range(b.lineno, b.end_lineno + 1))
    n = 0
    for i, ln in enumerate(src_lines, 1):
        s = ln.strip()
        if not s or s.startswith('#') or i in doc_lines:
            continue
        n += 1
    return n


def call_graph(trees, modname):
    """Symbol-level call graph.

    The module graph is the wrong granularity for many refactorings: inlining
    a helper removes a CALL edge but no module edge. A structural measure that
    cannot see inlining is measuring the wrong thing. This resolves
    intra-package call sites against module-level definitions and imported
    symbols.
    """
    # (module, qualname) for every module-level def/class
    defs = {}
    # per module: name -> (module, qualname)
    scope = {}
    for m, (tree, _, _) in trees.items():
        sc = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                key = (m, node.name)
                defs[key] = node
                sc.setdefault(node.name, key)
        scope[m] = sc

    # fold intra-package imports into scope
    for m, (tree, _, _) in trees.items():
        ic = ImportCollector(m, modname)
        ic.visit(tree)
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                base = n.module or ''
                if n.level == 1 and not base:
                    for a in n.names:
                        if (m, a.name) in defs:
                            scope[m].setdefault(a.asname or a.name, (m, a.name))
                elif base and base.split('.')[-1] in trees:
                    src = base
                    for a in n.names:
                        if (src, a.name) in defs:
                            scope[m].setdefault(a.asname or a.name, (src, a.name))
            elif isinstance(n, ast.Import):
                for a in n.names:
                    parts = a.name.split('.')
                    for cut in range(len(parts) - 1, 0, -1):
                        cand = '.'.join(parts[:cut])
                        if (cand, a.asname or parts[cut]) in defs:
                            scope[m].setdefault(a.asname or a.name, (cand, a.asname or parts[cut]))

    def walk_calls(node, m, out):
        sc = scope.get(m, {})
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id in sc:
                out.add(sc[n.func.id])

    edges = set()
    # every function/method in the package is a call-graph node, not just
    # module-level definitions -- otherwise edge endpoints dangle.
    callers = set()
    for m, (tree, _, _) in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                callers.add((m, node.name))
    for m, (tree, _, _) in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller = (m, node.name)
                out = set()
                walk_calls(node, m, out)
                for c in out:
                    if c != caller and c in callers:
                        edges.add((caller, c))
        # module-level calls
        out = set()
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef)):
                walk_calls(node, m, out)
    return callers, edges


def analyze(root, pkgdir=None, modname=None, exclude_ops=()):
    """Return full metric dict for a repo root.

    pkgdir   : filesystem path of the package relative to root (e.g. 'src/black')
    modname  : the importable module prefix            (e.g. 'black')
    """
    root = os.path.abspath(root)
    if pkgdir is None:
        pkgdir = top_package(root)
    if not pkgdir:
        return None
    pkgroot = os.path.join(root, pkgdir)
    if not os.path.isdir(pkgroot):
        pkgroot = root
    if modname is None:
        modname = pkgdir.replace(os.sep, '.')

    files = [f for f in repo_files(pkgroot)]
    mod_of = {}
    for f in files:
        rel = os.path.relpath(f, pkgroot)
        if rel == '__init__.py':
            mod = modname
        else:
            rel = rel[:-3]                       # strip .py
            mod = modname + '.' + rel.replace(os.sep, '.') if modname else rel.replace(os.sep, '.')
            if mod.endswith('.__init__'):
                mod = mod[:-len('.__init__')]
        mod_of[f] = mod

    trees, parse_fail = {}, 0
    for f, m in mod_of.items():
        try:
            with open(f, 'r', encoding='utf-8', errors='replace') as fh:
                src = fh.read()
            trees[m] = (ast.parse(src, filename=f), src.splitlines(), f)
        except (SyntaxError, ValueError, UnicodeError, RecursionError):
            parse_fail += 1

    # ---- Axis S : module dependency graph
    adj, ext = defaultdict(set), defaultdict(set)
    for m, (tree, _, _) in trees.items():
        ic = ImportCollector(m, modname)
        ic.visit(tree)
        for e in ic.edges:
            if e in trees:
                adj[m].add(e)
        for e in ic.ext_edges:
            ext[m].add(e)

    nodes = list(trees)
    edges = {(a, b) for a in adj for b in adj[a] if a != b}
    fanout = {m: len(adj[m]) for m in nodes}
    fanin = defaultdict(int)
    for a, b in edges:
        fanin[b] += 1
    depth = _max_depth(nodes, edges)
    scc = _scc_count(nodes, edges)
    # graph cyclomatic complexity E - V + 2P
    ncomp = _ncomp(nodes, edges)
    gcc = max(1, len(edges) - len(nodes) + 2 * ncomp)

    # ---- Axis S2 : symbol-level call graph
    try:
        cg_nodes, cg_edges = call_graph(trees, modname)
        cg_n = list(cg_nodes)
        cg_d = _max_depth(cg_n, cg_edges)
        cg_fanout = sum(1 for a, b in cg_edges)
        cg_fanin = defaultdict(int)
        for a, b in cg_edges:
            cg_fanin[b] += 1
        cg_gcc = max(1, len(cg_edges) - len(cg_n) + 2 * _ncomp(cg_n, cg_edges))
        cg_roots = sum(1 for n in cg_n if cg_fanin[n] == 0)
    except RecursionError:
        cg_n, cg_edges, cg_d, cg_fanout, cg_gcc, cg_roots = [], set(), 0, 0, 1, 0
        cg_fanin = {}

    # ---- Axis C : coupling / interface exposure
    pub = priv = 0
    pub_names_per_mod = {}
    for m, (tree, _, _) in trees.items():
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name.startswith('_') and not node.name.startswith('__'):
                    priv += 1
                else:
                    pub += 1
                    names.add(node.name)
        # module-level assigned constants
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and not t.id.startswith('_'):
                        pub += 1
                        names.add(t.id)
        pub_names_per_mod[m] = names

    total_iface = pub + priv
    # cross-package import ratio
    pkg_set = set()
    for m in nodes:
        parts = m.split('.')
        if len(parts) > 1:
            pkg_set.add('.'.join(parts[:2]) if modname and parts[0] == modname else parts[0])
    cross = sum(1 for a, b in edges if _sub(a, modname) != _sub(b, modname))
    cross_ratio = cross / len(edges) if edges else 0.0
    ext_ratio = sum(len(ext[m]) for m in nodes) / max(1, len(nodes))
    instability = (sum(1 for a, b in edges if _sub(a, modname) != _sub(b, modname)) /
                   max(1, len(edges))) if edges else 0.0

    # ---- Axis L : intra-procedural decision complexity
    ccs, procs, max_cc = [], 0, 0
    for m, (tree, _, _) in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                v = proc_stats(node)
                ccs.append(v.cc)
                max_cc = max(max_cc, v.cc)
                procs += 1
    mean_cc = sum(ccs) / len(ccs) if ccs else 1.0
    p90 = _pct(ccs, 0.90)
    max_depth_in_proc = 0
    for m, (tree, _, _) in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                max_depth_in_proc = max(max_depth_in_proc, proc_stats(node).max_depth)

    # ---- Axis L2 : expression-level statement complexity
    ex = [expr_stats(tree) for tree, _, _ in trees.values()]
    max_enest = max((e.max_depth for e in ex), default=0)
    # exclude the package __init__ re-export wall: it is a flat import list,
    # not logic, and would dominate the mean
    core = [e for e, (tree, _, _) in zip(ex, trees.values())
            if not tree.body or not _is_reexport_only(tree)]
    tot_calls = sum(e.calls for e in core)
    tot_bool = sum(e.boolops for e in core)
    bool_density = tot_bool / max(1, tot_calls)
    mean_enest = sum(e.max_depth for e in core) / max(1, len(core))

    # ---- size / constraints
    sloc = 0
    for m, (tree, lines, _) in trees.items():
        sloc += _effective_lines(lines, tree)
    # formatting-invariant size: AST statement count. ast.unparse reflows
    # multi-line expressions onto one line, so a line-based SLOC is NOT stable
    # across codegen; statement count is.
    stmt = sum(1 for m, (tree, _, _) in trees.items()
               for n in ast.walk(tree) if isinstance(n, ast.stmt))
    api_fingerprint = hashlib.sha256(
        '\n'.join(sorted(f"{m}:{n}" for m, ns in pub_names_per_mod.items()
                         for n in ns)).encode()).hexdigest()[:16]

    return {
        'pkg': modname, 'files': len(trees), 'parse_fail': parse_fail,
        'procs': procs, 'sloc': sloc,
        # Axis S
        'S_edges': len(edges),
        'S_fanout': sum(fanout.values()) / max(1, len(nodes)),
        'S_fanin': sum(fanin.values()) / max(1, len(nodes)),
        'S_depth': depth,
        'S_scc': scc,
        'S1_maxfanin': max(fanin.values()) if fanin else 0,
        'S1_maxfanout': max(fanout.values()) if fanout else 0,
        # Axis S2 (symbol granularity)
        'S2_funcs': len(cg_n),
        'S2_edges': len(cg_edges),
        'S2_depth': cg_d,
        'S2_gcc': cg_gcc,
        'S2_fanout': cg_fanout / max(1, len(cg_n)),
        'S2_maxfanin': max(cg_fanin.values()) if cg_fanin else 0,
        'S_gcc': gcc,
        # Axis C
        'C_public': pub, 'C_private': priv,
        'C_exposure': pub / max(1, total_iface),
        'C_cross_ratio': cross_ratio,
        'C_ext_ratio': ext_ratio,
        'C_instability': instability,
        # Axis L
        'L_mean_cc': mean_cc,
        'L_p90_cc': p90,
        'L_max_cc': max_cc,
        'L_nesting': max_depth_in_proc,
        'L_max_enest': max_enest,
        'L_mean_enest': mean_enest,
        'L_bool_density': bool_density,
        # constraints
        'K_sloc': sloc,
        'K_stmt': stmt,
        'K_api': api_fingerprint,
    }


def _is_reexport_only(tree):
    """True if every top-level stmt is an import or a re-export alias."""
    for n in tree.body:
        if not isinstance(n, (ast.Import, ast.ImportFrom, ast.Assign, ast.Expr)):
            return False
        if isinstance(n, ast.Expr) and not isinstance(n.value, ast.Constant):
            return False
    return True


def _sub(m, pkg):
    return '.'.join(m.split('.')[:2]) if pkg and m.startswith(pkg) and \
        len(m.split('.')) > 1 else m.split('.')[0]


def _pct(xs, q):
    if not xs:
        return 0.0
    s = sorted(xs)
    i = int(q * (len(s) - 1))
    return float(s[i])


def _ncomp(nodes, edges):
    par = {n: n for n in nodes}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb
    return len({find(n) for n in nodes})


def _tarjan_scc(nodes, edges):
    """Tarjan SCC -> (comp_id per node, condensation edges, n_comp)."""
    adj = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
    index, low, on, stk, comp = {}, {}, set(), [], {}
    counter = [0]
    ncomp = 0

    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, pi = work[-1]
            if pi == 0:
                index[v] = low[v] = counter[0]
                counter[0] += 1
                stk.append(v); on.add(v)
            recurse = False
            for i in range(pi, len(adj[v])):
                w = adj[v][i]
                if w not in index:
                    work[-1] = (v, i + 1)
                    work.append((w, 0))
                    recurse = True
                    break
                elif w in on:
                    low[v] = min(low[v], index[w])
            if recurse:
                continue
            work.pop()
            if work:
                pv = work[-1][0]
                low[pv] = min(low[pv], low[v])
            if low[v] == index[v]:
                while True:
                    w = stk.pop(); on.discard(w)
                    comp[w] = ncomp
                    if w == v:
                        break
                ncomp += 1
    cond = set()
    for a, b in edges:
        if comp[a] != comp[b]:
            cond.add((comp[a], comp[b]))
    return comp, cond, ncomp


def _max_depth(nodes, edges):
    """Longest path in the SCC-condensed DAG (cycle-safe, exact)."""
    if not nodes:
        return 0
    comp, cond, nc = _tarjan_scc(nodes, edges)
    cadj = defaultdict(list)
    indeg = {i: 0 for i in range(nc)}
    for a, b in cond:
        cadj[a].append(b)
        indeg[b] += 1
    from collections import deque
    q = deque(i for i in range(nc) if indeg[i] == 0)
    d = {i: 1 for i in range(nc)}
    seen = 0
    while q:
        u = q.popleft(); seen += 1
        for v in cadj[u]:
            if d[v] < d[u] + 1:
                d[v] = d[u] + 1
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return max(d.values()) if d else 0


def _max_depth_cyclic(nodes, edges):
    return _max_depth(nodes, edges)


def _scc_count(nodes, edges):
    return _ncomp(nodes, edges)
