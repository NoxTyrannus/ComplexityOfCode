"""Experiment driver: apply each operator to each repo, measure the three axes,
and evaluate the non-gameability constraints."""
import os
import sys
import ast
import json
import shutil
import tempfile
import hashlib
from collections import defaultdict

sys.setrecursionlimit(50000)
import analyze
import transform
import repos

CONSTRAINTS = {
    'K1_compiles':   None,   # every file must compile
    'K2_stmt_floor': 0.90,   # statement count must stay >= 90% of baseline
    'K3_api_intact': None,   # every baseline public symbol must still be defined
    'K4_no_new_dep': None,   # no NEW external dependency may appear
    'K5_no_new_hub': 1.15,   # max fan-in must not grow by >15% (hub avoidance)
}


def load_repo(name, pdir):
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', name))
    pkgroot = os.path.join(root, pdir)
    files = {}
    for dp, dn, fn in os.walk(pkgroot):
        dn[:] = [d for d in dn if d not in ('.git', '__pycache__', 'tests', 'test')]
        for f in fn:
            if not f.endswith('.py'):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, pkgroot).replace(os.sep, '/')
            try:
                files[rel] = open(p, encoding='utf-8', errors='replace').read()
            except Exception:
                pass
    return root, pdir, files


def api_set(files):
    out = set()
    for k, src in files.items():
        try:
            t = ast.parse(src)
        except SyntaxError:
            continue
        for n in t.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.add((k, n.name))
            elif isinstance(n, ast.Assign):
                for tg in n.targets:
                    if isinstance(tg, ast.Name):
                        out.add((k, tg.id))
    return out


def api_public(files):
    return {(k, n) for k, n in api_set(files) if not n.startswith('_')}


def ext_imports(files):
    """Top-level external modules imported anywhere."""
    out = set()
    for k, src in files.items():
        try:
            t = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(t):
            if isinstance(n, ast.Import):
                for a in n.names:
                    out.add(a.name.split('.')[0])
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                out.add(n.module.split('.')[0])
    return out


def stmt_of(files):
    """Formatting-invariant size: AST statement count.

    A line-based SLOC is NOT usable here: ast.unparse reflows multi-line
    expressions onto a single line, so reformatting alone moves SLOC by >20%
    and would swamp every signal we are trying to measure.
    """
    tot = 0
    for k, src in files.items():
        try:
            t = ast.parse(src)
        except SyntaxError:
            continue
        tot += sum(1 for n in ast.walk(t) if isinstance(n, ast.stmt))
    return tot


def write_and_analyze(root, pdir, modname, files, tag):
    """Materialise a file map into a temp copy of the repo and analyze it."""
    d = tempfile.mkdtemp(prefix=f'cx_{tag}_')
    pkgroot = os.path.join(d, pdir)
    os.makedirs(pkgroot, exist_ok=True)
    for rel, src in files.items():
        p = os.path.join(pkgroot, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(src)
    try:
        m = analyze.analyze(d, pkgdir=pdir, modname=modname)
    except Exception as e:
        m = None
        print(f'   !! analyze failed {tag}: {type(e).__name__} {e}')
    shutil.rmtree(d, ignore_errors=True)
    return m


AXES = {
    'S': ['S_edges', 'S_fanout', 'S_depth', 'S_gcc'],
    'C': ['C_exposure', 'C_cross_ratio', 'C_ext_ratio'],
    'L': ['L_mean_cc', 'L_p90_cc', 'L_nesting'],
}


def main():
    results = []
    for name, (pdir, modname) in repos.REPOS.items():
        root, _, base_files = load_repo(name, pdir)
        if not base_files:
            print(f'-- {name}: no files'); continue
        base = analyze.analyze(root, pkgdir=pdir, modname=modname)
        if not base:
            print(f'-- {name}: analyze failed'); continue

        b_api = api_public(base_files)
        b_sloc = stmt_of(base_files)
        b_ext = ext_imports(base_files)
        print(f'== {name}  files={len(base_files)} stmt={b_sloc} '
              f'api={len(b_api)} ext={len(b_ext)}')

        # every operator is applied ON TOP OF the noop control, and every
        # comparison is against the noop control. This removes the reflow
        # artifact of ast.unparse from every measured delta.
        transform.PKG = modname
        noop_files = transform.OPERATORS['noop'](dict(base_files))
        noop_metrics = write_and_analyze(root, pdir, modname, noop_files,
                                         f'{name}_noopctl')
        noop_stmt = stmt_of(noop_files)
        for opname, op in transform.OPERATORS.items():
            if opname == 'noop':
                continue
            transform.PKG = modname
            try:
                new_files = op(dict(noop_files))
            except Exception as e:
                print(f'   {opname:9s} EXC {type(e).__name__}: {e}')
                continue
            if not new_files:
                continue

            ok, badfile = transform.validate(new_files)
            n_sloc = stmt_of(new_files)
            n_api = api_public(new_files)
            n_ext = ext_imports(new_files)
            lost = len(b_api - n_api)
            new_dep = sorted(n_ext - b_ext)

            # K5 evaluated after analysis, since it needs the call graph
            cons = {
                'K1_compiles': ok,
                'K2_stmt_floor': n_sloc >= CONSTRAINTS['K2_stmt_floor'] * noop_stmt,
                'K3_api_intact': lost == 0,
                'K4_no_new_dep': len(new_dep) == 0,
            }
            metrics = write_and_analyze(root, pdir, modname, new_files,
                                        f'{name}_{opname}')
            if not metrics:
                continue
            ref = noop_metrics or base
            def pct(k):
                r, m = ref.get(k), metrics.get(k)
                if r in (None, 0) or m is None:
                    return 0.0
                return 100.0 * (m - r) / abs(r)
            deltas = {k: pct(k) for k in
                      ('S_edges', 'S_fanout', 'S_depth', 'S_gcc',
                       'S2_edges', 'S2_depth', 'S2_gcc', 'S2_fanout',
                       'S2_maxfanin',
                       'C_exposure', 'C_cross_ratio', 'C_ext_ratio',
                       'L_mean_cc', 'L_p90_cc', 'L_nesting',
                       'L_max_enest', 'L_mean_enest', 'L_bool_density')}
            # The hub anti-pattern lives on the MODULE import graph, not the
            # call graph: routing imports through a gateway concentrates
            # in-degree on one module. Measure it there.
            ref_fi = (ref or {}).get('S1_maxfanin', 0)
            new_fi = metrics.get('S1_maxfanin', 0)
            hub_ok = new_fi <= CONSTRAINTS['K5_no_new_hub'] * max(1, ref_fi)
            cons['K5_no_new_hub'] = bool(hub_ok)
            changed = any(abs(v) > 0.01 for v in deltas.values())
            results.append({
                'repo': name, 'op': opname, 'metrics': metrics,
                'base': base, 'cons': cons,
                'stmt_before': b_sloc, 'stmt_after': n_sloc, 'stmt_noop': noop_stmt,
                'api_lost': lost, 'new_deps': new_dep,
                'n_files_before': len(base_files), 'n_files_after': len(new_files),
                'changed': changed,
                'noop_metrics': noop_metrics,
                'ref': ref,
                'deltas': deltas,
            })
            print(f'   {opname:9s} f{len(noop_files):4d}->{len(new_files):4d} '
                  f'stm{noop_stmt:6d}->{n_sloc:6d} | '
                  f'dS1{deltas["S_edges"]:+6.1f}% dS2{deltas["S2_edges"]:+6.1f}% '
                  f'dC {deltas["C_cross_ratio"]:+6.2f}pp '
                  f'dL {deltas["L_mean_cc"]:+6.2f} en{metrics["L_max_enest"]:3d}->{ref["L_max_enest"]:<3d} | '
                  f'K:{sum(cons.values())}/5 hub{ref_fi}->{new_fi}'
                  + (f' api_lost={lost}' if lost else ''))

    json.dump(results, open(os.path.join(os.path.dirname(__file__), '..',
                                        'out', 'raw.json'), 'w'), indent=1)
    print(f'\nsaved {len(results)} (repo, operator) cells')


if __name__ == '__main__':
    main()
