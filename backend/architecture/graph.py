"""Conservative symbol graph over indexed entities. No target execution."""

import ast
import posixpath
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import PurePosixPath

from backend.analysis import javascript_parser as js
from backend.analysis.engine import read_indexed_source

MAX_NODES = 5000
MAX_EDGES = 20000
CALLABLE = {"function", "method", "class"}


def module_name(path):
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts[-1] in {"__init__", "index"}:
        parts.pop()
    return ".".join(parts)


def build_graph(root, files, entities):
    nodes, edges, unresolved = {}, {}, []
    paths = {f.path for f in files}
    by_key = {e.key: e for e in entities}
    modules = defaultdict(list)
    symbols = defaultdict(list)
    local = defaultdict(list)
    for file in files:
        modules[module_name(file.path)].append(file.path)
    for entity in entities:
        if entity.kind in CALLABLE:
            local[(entity.file, entity.parent, entity.name)].append(entity)
            if entity.parent is None:
                symbols[f"{module_name(entity.file)}.{entity.name}"].append(entity)
    # Shadowed parameter/local names must not be mistaken for module functions.
    shadows = defaultdict(set)
    for file in files:
        if file.language in {"JavaScript", "TypeScript"} and file.size_bytes <= 512 * 1024:
            try:
                capsule = (
                    js.tree_sitter_javascript.language()
                    if file.language == "JavaScript"
                    else js.tree_sitter_typescript.language_tsx()
                    if file.path.endswith(".tsx")
                    else js.tree_sitter_typescript.language_typescript()
                )
                tree = js.Parser(js.Language(capsule)).parse(
                    read_indexed_source(root, file.path, file.sha256, 512 * 1024).encode()
                )
                for node in js.walk(tree.root_node):
                    if node.type not in js.FUNCTION_TYPES:
                        continue
                    params = node.child_by_field_name("parameters") or node.child_by_field_name("parameter")
                    names = {
                        js.text(n)
                        for n in ([params, *js.walk(params)] if params else [])
                        if n.type == "identifier"
                    }
                    for child in js.walk(node, skip_scopes=True):
                        if child.type == "variable_declarator":
                            name = child.child_by_field_name("name")
                            if name and name.type == "identifier":
                                names.add(js.text(name))
                    scope_name = js.name_of(node.child_by_field_name("name"))
                    if not scope_name and node.parent and node.parent.type == "variable_declarator":
                        scope_name = js.name_of(node.parent.child_by_field_name("name"))
                    shadows[(file.path, node.start_point.row + 1, scope_name or "<anonymous>")] = names
            except (ValueError, OSError, RecursionError):
                shadows[(file.path, -1)] = {"*"}
        if file.language != "Python" or file.size_bytes > 512 * 1024:
            continue
        try:
            tree = ast.parse(read_indexed_source(root, file.path, file.sha256, 512 * 1024))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                names = {arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
                if node.args.vararg:
                    names.add(node.args.vararg.arg)
                if node.args.kwarg:
                    names.add(node.args.kwarg.arg)
                pending = list(ast.iter_child_nodes(node))
                while pending:
                    child = pending.pop()
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                        names.add(child.id)
                    if not isinstance(
                        child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
                    ):
                        pending.extend(ast.iter_child_nodes(child))
                shadows[(file.path, node.lineno, node.name)] = names
        except (ValueError, OSError, SyntaxError, RecursionError):
            shadows[(file.path, -1)] = {"*"}

    def add_node(key, **data):
        if len(nodes) < MAX_NODES:
            nodes.setdefault(key, {"id": key, **data})

    def edge(source, target, kind, file, line, basis):
        if source in nodes and target in nodes and len(edges) < MAX_EDGES:
            key = (source, target, kind)
            edges.setdefault(
                key,
                {
                    "source": source,
                    "target": target,
                    "kind": kind,
                    "file": file,
                    "line": line,
                    "basis": basis,
                },
            )

    for file in files:
        add_node(
            "file:" + file.path, kind="file", name=file.path, file=file.path, line=1, language=file.language
        )
    for entity in entities:
        if entity.kind not in CALLABLE | {"api"}:
            continue
        add_node(
            entity.key,
            kind=entity.kind,
            name=entity.name,
            file=entity.file,
            line=entity.start_line,
            end_line=entity.end_line,
            language=entity.language,
            complexity=entity.complexity,
        )
    for entity in entities:
        if entity.key in nodes:
            parent = entity.parent if entity.parent in nodes else "file:" + entity.file
            edge(
                parent,
                entity.key,
                "exposes" if entity.kind == "api" else "contains",
                entity.file,
                entity.start_line,
                "AST lexical containment",
            )

    def import_target(entity):
        name = entity.name
        if entity.language == "Python":
            if name.startswith("."):
                count = len(name) - len(name.lstrip("."))
                package = list(PurePosixPath(entity.file).parent.parts)
                prefix = package[: max(0, len(package) - count + 1)]
                name = ".".join([*prefix, name.lstrip(".")]).strip(".")
            while name:
                if len(modules[name]) == 1:
                    return modules[name][0]
                name = name.rpartition(".")[0]
        elif name.startswith("."):
            base = posixpath.normpath(posixpath.join(posixpath.dirname(entity.file), name))
            candidates = [
                base,
                *[base + suffix for suffix in (".ts", ".tsx", ".js", ".jsx")],
                *[base + "/index" + suffix for suffix in (".ts", ".tsx", ".js", ".jsx")],
            ]
            found = [p for p in candidates if p in paths]
            if len(found) == 1:
                return found[0]
        return None

    for entity in entities:
        if entity.kind != "import":
            continue
        target = import_target(entity)
        if target:
            edge(
                "file:" + entity.file,
                "file:" + target,
                "imports",
                entity.file,
                entity.start_line,
                "Import matches an indexed module path",
            )
        else:
            key = "external:" + sha256(entity.name.encode()).hexdigest()
            add_node(key, kind="external", name=entity.name, file=None, line=None, language=entity.language)
            edge(
                "file:" + entity.file,
                key,
                "depends_on",
                entity.file,
                entity.start_line,
                "Unresolved or external import reference; installation is not verified",
            )

    for entity in entities:
        if entity.kind not in {"function", "method"}:
            continue
        for name in entity.callees:
            candidates = []
            shadowed = (
                name.split(".")[0] in shadows[(entity.file, entity.start_line, entity.name)]
                or shadows[(entity.file, -1)]
            )
            if not shadowed or (name.startswith("self.") and entity.kind == "method"):
                if name.startswith("self.") and entity.parent:
                    candidates = local[(entity.file, entity.parent, name[5:])]
                elif "." not in name:
                    # Resolve nearest lexical scope, then module. Nested closures are bounded.
                    scope = entity.key
                    for _ in range(20):
                        # Class namespaces are not enclosing lexical function scopes.
                        if scope in by_key and by_key[scope].kind == "class":
                            scope = by_key[scope].parent
                        candidates = local[(entity.file, scope, name)]
                        if candidates or scope is None:
                            break
                        parent = by_key.get(scope)
                        scope = parent.parent if parent else None
                        if parent and parent.kind == "class":
                            scope = None
                elif entity.language == "Python":
                    candidates = symbols[name]
            if len(candidates) == 1:
                target = candidates[0]
                edge(
                    entity.key,
                    target.key,
                    "calls",
                    entity.file,
                    entity.start_line,
                    f"Unique lexical target for {name}; static reference, not runtime dispatch proof",
                )
            elif len(unresolved) < MAX_EDGES:
                unresolved.append(
                    {
                        "source": entity.key,
                        "file": entity.file,
                        "line": entity.start_line,
                        "name": name,
                        "reason": "Shadowed, external, dynamic, or ambiguous target",
                    }
                )
    all_edges = list(edges.values())
    fan_in, fan_out = Counter(), Counter()
    adjacency = defaultdict(set)
    for item in all_edges:
        if item["kind"] not in {"imports", "calls"}:
            continue
        source, target = nodes[item["source"]].get("file"), nodes[item["target"]].get("file")
        if source and target and source != target:
            adjacency[source].add(target)
    for source, targets in adjacency.items():
        fan_out[source] = len(targets)
        for target in targets:
            fan_in[target] += 1
    cycles = strongly_connected(adjacency)
    return {
        "version": "1.0",
        "nodes": list(nodes.values()),
        "edges": all_edges,
        "unresolved": unresolved,
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "resolved_calls": sum(e["kind"] == "calls" for e in all_edges),
            "unresolved_calls": len(unresolved),
            "cycles": cycles,
            "coupling": [{"file": p, "fan_in": fan_in[p], "fan_out": fan_out[p]} for p in sorted(paths)],
            "truncated": len(nodes) >= MAX_NODES or len(edges) >= MAX_EDGES or len(unresolved) >= MAX_EDGES,
            "scope": "Lexical references for Python/JS/TS; dynamic dispatch, JS cross-file calls, inheritance, and read/write flows are not resolved.",
        },
    }


def strongly_connected(adjacency):
    """Iterative Kosaraju: bounded by graph size without recursion-depth failures."""
    vertices = set(adjacency) | {v for values in adjacency.values() for v in values}
    seen, order = set(), []
    for root in sorted(vertices):
        if root in seen:
            continue
        stack = [(root, False)]
        while stack:
            node, exiting = stack.pop()
            if exiting:
                order.append(node)
                continue
            if node in seen:
                continue
            seen.add(node)
            stack.append((node, True))
            stack.extend(
                (child, False) for child in sorted(adjacency.get(node, ()), reverse=True) if child not in seen
            )
    reverse = defaultdict(set)
    for source, targets in adjacency.items():
        for target in targets:
            reverse[target].add(source)
    seen, result = set(), []
    for root in reversed(order):
        if root in seen:
            continue
        component, stack = [], [root]
        seen.add(root)
        while stack:
            node = stack.pop()
            component.append(node)
            for child in reverse[node]:
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        if len(component) > 1:
            result.append(sorted(component))
    return sorted(result)
