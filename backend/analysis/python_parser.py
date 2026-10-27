"""Python AST parsing and conservative local rules; target modules are never imported."""

import ast
import re

from backend.analysis.contracts import Detection, Entity, ParsedFile, entity_key

SECRET_NAME = re.compile(r"(?:password|passwd|secret|api_?key|access_?token|private_?key)", re.IGNORECASE)
SECURITY_CONTEXT = re.compile(r"token|password|nonce|secret|reset", re.IGNORECASE)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return call_name(node.func)
    return ""


def scope_nodes(root: ast.AST):
    pending = list(ast.iter_child_nodes(root))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, SCOPES):
            pending.extend(ast.iter_child_nodes(node))


def parse_python(path: str, source: str) -> ParsedFile:
    output = ParsedFile()
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, RecursionError, ValueError) as error:
        line = getattr(error, "lineno", None)
        output.parsed = False
        output.warnings.append(f"Python parse failed: {path}" + (f":{line}" if line else ""))
        return output
    nodes = list(ast.walk(tree))
    if len(nodes) > 75_000:
        return ParsedFile(warnings=[f"AST node limit exceeded: {path}"], parsed=False)
    parents = {child: parent for parent in nodes for child in ast.iter_child_nodes(parent)}
    aliases: dict[str, str] = {}
    for node in nodes:
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = (
                    item.name if item.asname else item.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module or ''}.{item.name}".lstrip(".")

    def qualified(node: ast.AST) -> str:
        name = call_name(node)
        first, _, rest = name.partition(".")
        return aliases.get(first, first) + (f".{rest}" if rest else "")

    def scope_for(node: ast.AST) -> ast.AST:
        current = parents.get(node)
        while current is not None and not isinstance(current, SCOPES):
            current = parents.get(current)
        return current or tree

    # Bind expressions per lexical scope and resolve only assignments before the
    # use site. This is deliberately not a whole-program taint analysis.
    bindings: dict[ast.AST, dict[str, list[tuple[int, ast.AST]]]] = {}
    for node in nodes:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    bindings.setdefault(scope_for(node), {}).setdefault(target.id, []).append(
                        (node.lineno, node.value)
                    )

    def resolve(node: ast.AST, scope: ast.AST, before: int, seen: frozenset[str] = frozenset()) -> ast.AST:
        if isinstance(node, ast.Name) and node.id not in seen:
            choices = [
                (line, value) for line, value in bindings.get(scope, {}).get(node.id, []) if line < before
            ]
            if choices:
                line, value = max(choices, key=lambda item: item[0])
                return resolve(value, scope, line, seen | {node.id})
        return node

    def dynamic(node: ast.AST, scope: ast.AST, before: int) -> bool:
        node = resolve(node, scope, before)
        if isinstance(node, ast.Constant):
            return False
        if isinstance(node, ast.JoinedStr):
            return any(
                isinstance(item, ast.FormattedValue) and dynamic(item.value, scope, before)
                for item in node.values
            )
        if isinstance(node, ast.BinOp):
            return dynamic(node.left, scope, before) or dynamic(node.right, scope, before)
        return True

    def string_built(node: ast.AST, scope: ast.AST, before: int) -> bool:
        node = resolve(node, scope, before)
        return dynamic(node, scope, before) and (
            isinstance(node, (ast.JoinedStr, ast.BinOp))
            or isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
        )

    def parameter_path(node: ast.AST, scope: ast.AST, before: int) -> bool:
        if not isinstance(scope, FUNCTIONS):
            return False
        params = {arg.arg for arg in [*scope.args.posonlyargs, *scope.args.args, *scope.args.kwonlyargs]}
        resolved = resolve(node, scope, before)
        return any(isinstance(item, ast.Name) and item.id in params for item in ast.walk(resolved))

    scopes: dict[ast.AST, str] = {}
    for node in nodes:
        if isinstance(node, SCOPES):
            name = getattr(node, "name", "<lambda>")
            kind = (
                "class"
                if isinstance(node, ast.ClassDef)
                else "method"
                if isinstance(scope_for(node), ast.ClassDef)
                else "function"
            )
            scopes[node] = entity_key(path, kind, name, node.lineno)

    def emit(rule: str, node: ast.AST, basis: str) -> None:
        scope = scope_for(node)
        output.detections.append(
            Detection(
                rule,
                path,
                "Python",
                node.lineno,
                getattr(node, "end_lineno", node.lineno),
                getattr(node if isinstance(node, SCOPES) else scope, "name", "<module>"),
                basis,
            )
        )

    for node in nodes:
        scope = scope_for(node)
        parent_key = scopes.get(scope)
        if isinstance(node, SCOPES):
            name = getattr(node, "name", "<lambda>")
            body = list(scope_nodes(node))
            complexity = 1 + sum(
                isinstance(
                    n,
                    (
                        ast.If,
                        ast.IfExp,
                        ast.For,
                        ast.AsyncFor,
                        ast.While,
                        ast.ExceptHandler,
                        ast.comprehension,
                        ast.match_case,
                    ),
                )
                for n in body
            )
            complexity += sum(len(n.values) - 1 for n in body if isinstance(n, ast.BoolOp))
            calls = sorted({qualified(n.func) for n in body if isinstance(n, ast.Call)})[:500]
            features = []
            if any(isinstance(n, (ast.For, ast.AsyncFor, ast.While, ast.comprehension)) for n in body):
                features.append("loops")
            if any(isinstance(n, (ast.If, ast.IfExp)) for n in body):
                features.append("conditions")
            if any(isinstance(n, ast.Try) for n in body):
                features.append("exception_handling")
            if any(name.rsplit(".", 1)[-1] in {"execute", "executemany"} for name in calls):
                features.append("database_operations")
            if any(
                name.rsplit(".", 1)[-1] in {"open", "read_bytes", "read_text", "write_text", "write_bytes"}
                for name in calls
            ):
                features.append("file_operations")
            if re.search(r"auth|login|permission|admin", name, re.IGNORECASE):
                features.append("authentication_logic")
            kind = (
                "class"
                if isinstance(node, ast.ClassDef)
                else "method"
                if isinstance(scope, ast.ClassDef)
                else "function"
            )
            output.entities.append(
                Entity(
                    scopes[node],
                    path,
                    "Python",
                    kind,
                    name[:255],
                    node.lineno,
                    node.end_lineno or node.lineno,
                    parent_key,
                    [qualified(base) for base in node.bases] if isinstance(node, ast.ClassDef) else [],
                    [],
                    calls,
                    complexity,
                    features,
                )
            )
            if isinstance(node, FUNCTIONS):
                if complexity > 10:
                    emit(
                        "QUAL-002",
                        node,
                        f"Function complexity is {complexity}; threshold is 10 decision paths.",
                    )
                if (node.end_lineno or node.lineno) - node.lineno + 1 > 80:
                    emit(
                        "QUAL-003",
                        node,
                        f"Function spans {(node.end_lineno or node.lineno) - node.lineno + 1} lines; threshold is 80.",
                    )
                for decorator in getattr(node, "decorator_list", []):
                    if isinstance(decorator, ast.Call) and call_name(decorator.func).rsplit(".", 1)[-1] in {
                        "get",
                        "post",
                        "put",
                        "delete",
                        "patch",
                        "route",
                    }:
                        output.entities.append(
                            Entity(
                                entity_key(path, "api", name, decorator.lineno),
                                path,
                                "Python",
                                "api",
                                name,
                                decorator.lineno,
                                node.end_lineno or node.lineno,
                                scopes[node],
                            )
                        )
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            dependencies = [
                f"{'.' * node.level}{node.module}.{item.name}"
                if isinstance(node, ast.ImportFrom) and node.module
                else f"{'.' * node.level}{item.name}" if isinstance(node, ast.ImportFrom) else item.name
                for item in node.names
            ]
            for name in dependencies:
                output.entities.append(
                    Entity(
                        entity_key(path, "import", name, node.lineno),
                        path,
                        "Python",
                        "import",
                        name[:255],
                        node.lineno,
                        node.end_lineno or node.lineno,
                        parent_key,
                        dependencies=[name],
                    )
                )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                name = call_name(target)
                if not name:
                    continue
                output.entities.append(
                    Entity(
                        entity_key(path, "variable", name, node.lineno),
                        path,
                        "Python",
                        "variable",
                        name[:255],
                        node.lineno,
                        node.end_lineno or node.lineno,
                        parent_key,
                    )
                )
                if (
                    SECRET_NAME.search(name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    and len(node.value.value) >= 8
                ):
                    emit(
                        "SEC-001",
                        node,
                        "Secret-like assignment contains a literal of at least 8 characters; literal value redacted.",
                    )
        elif isinstance(node, ast.ExceptHandler) and all(isinstance(item, ast.Pass) for item in node.body):
            emit("QUAL-001", node, "Exception handler body contains only pass statements.")
        elif isinstance(node, ast.Compare) and re.search(
            r"admin|authorize|permission", getattr(scope, "name", ""), re.IGNORECASE
        ):
            if any(isinstance(n, ast.Constant) and n.value == "admin" for n in ast.walk(node)) and any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "get"
                and parameter_path(n.func.value, scope, node.lineno)
                and any(
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and "role" in arg.value.lower()
                    for arg in n.args
                )
                for n in ast.walk(node)
            ):
                emit(
                    "SEC-009",
                    node,
                    "Authorization-named function compares a parameter-derived role lookup to an admin literal.",
                )
        if not isinstance(node, ast.Call):
            continue
        name = qualified(node.func)
        leaf = name.rsplit(".", 1)[-1]
        first = node.args[0] if node.args else None
        keywords = {item.arg: item.value for item in node.keywords}
        if first is not None and leaf in {"execute", "executemany", "executescript"}:
            if string_built(first, scope, node.lineno):
                emit("SEC-002", node, "SQL execution receives a locally constructed dynamic string.")
            ancestor = parents.get(node)
            while ancestor is not None and not isinstance(ancestor, SCOPES):
                if isinstance(ancestor, (ast.For, ast.AsyncFor, ast.While, ast.comprehension)):
                    emit("PERF-001", node, "Database execution call is nested inside a loop.")
                    break
                ancestor = parents.get(ancestor)
        shell = isinstance(keywords.get("shell"), ast.Constant) and keywords["shell"].value is True
        if (
            first is not None
            and dynamic(first, scope, node.lineno)
            and (
                name in {"os.system", "os.popen", "subprocess.getoutput", "subprocess.getstatusoutput"}
                or name.startswith("subprocess.")
                and shell
            )
        ):
            emit("SEC-003", node, "Nonliteral command is passed to a shell-enabled execution API.")
        if first is not None and name in {"eval", "exec"} and dynamic(first, scope, node.lineno):
            emit("SEC-004", node, "Dynamic expression reaches Python code evaluation.")
        if (
            name
            in {"pickle.load", "pickle.loads", "dill.load", "dill.loads", "marshal.load", "marshal.loads"}
            or name == "yaml.load"
            and qualified(keywords.get("Loader", ast.Constant(None)))
            not in {"yaml.SafeLoader", "yaml.CSafeLoader"}
        ):
            emit("SEC-005", node, f"Call to unsafe object deserialization primitive {name}.")
        if name in {"hashlib.md5", "hashlib.sha1"}:
            emit(
                "SEC-006",
                node,
                f"Call to {name}; review whether collision resistance or password protection is required.",
            )
        if name.startswith("random.") and SECURITY_CONTEXT.search(getattr(scope, "name", "")):
            emit("SEC-007", node, f"Call to {name} in a security-token-named function.")
        file_input = (
            first
            if name in {"open", "io.open"}
            else node.func.value
            if isinstance(node.func, ast.Attribute)
            and leaf in {"read_bytes", "read_text", "write_bytes", "write_text", "unlink"}
            else None
        )
        if file_input is not None and parameter_path(file_input, scope, node.lineno):
            emit("SEC-008", node, "File-operation path contains a function parameter or a local derivative.")
        if (
            name
            in {
                f"{library}.{method}"
                for library in ("requests", "httpx")
                for method in ("get", "post", "put", "patch", "delete", "request")
            }
            and "timeout" not in keywords
        ):
            emit("REL-001", node, f"Call to {name} has no explicit timeout keyword.")
    return output
