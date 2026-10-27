"""Local Tree-sitter JavaScript/TypeScript/TSX parsing. No Node or target scripts run."""

from pathlib import Path

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from backend.analysis.contracts import Detection, Entity, ParsedFile, entity_key
from backend.analysis.python_parser import SECRET_NAME

FUNCTION_TYPES = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "generator_function_declaration",
    "method_definition",
}
SCOPE_TYPES = FUNCTION_TYPES | {"class_declaration", "class"}
DECISIONS = {
    "if_statement",
    "for_statement",
    "for_in_statement",
    "while_statement",
    "do_statement",
    "switch_case",
    "catch_clause",
    "ternary_expression",
}


def text(node: Node | None) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None and node.text else ""


def name_of(node: Node | None) -> str:
    if node is None:
        return ""
    if node.type in {"identifier", "property_identifier", "type_identifier"}:
        return text(node)[:255]
    if node.type == "member_expression":
        obj, prop = name_of(node.child_by_field_name("object")), name_of(node.child_by_field_name("property"))
        return f"{obj}.{prop}" if obj else prop
    return ""


def walk(node: Node, skip_scopes: bool = False):
    pending = list(reversed(node.named_children))
    while pending:
        item = pending.pop()
        yield item
        if not skip_scopes or item.type not in SCOPE_TYPES:
            pending.extend(reversed(item.named_children))


def parse_javascript(path: str, source: str, language: str) -> ParsedFile:
    capsule = (
        tree_sitter_javascript.language()
        if language == "JavaScript"
        else (
            tree_sitter_typescript.language_tsx()
            if Path(path).suffix.lower() == ".tsx"
            else tree_sitter_typescript.language_typescript()
        )
    )
    parser = Parser(Language(capsule))
    tree = parser.parse(source.encode("utf-8"))
    if tree.root_node.has_error:
        return ParsedFile(
            parsed=False, warnings=[f"{language} parse failed: {path}; findings withheld for invalid syntax."]
        )
    output = ParsedFile()
    nodes = list(walk(tree.root_node))
    if len(nodes) > 75_000:
        return ParsedFile(parsed=False, warnings=[f"AST node limit exceeded: {path}"])
    scope_keys: dict[int, str] = {}
    scope_names: dict[int, str] = {}
    bindings: dict[tuple[int, str], list[tuple[int, Node]]] = {}

    def scope_for(node: Node) -> Node:
        parent = node.parent
        while parent is not None and parent.type not in SCOPE_TYPES:
            parent = parent.parent
        return parent or tree.root_node

    for node in nodes:
        if node.type in SCOPE_TYPES:
            name = name_of(node.child_by_field_name("name"))
            if not name and node.parent and node.parent.type == "variable_declarator":
                name = name_of(node.parent.child_by_field_name("name"))
            name = name or "<anonymous>"
            scope_names[node.id] = name
            kind = (
                "class"
                if node.type in {"class", "class_declaration"}
                else "method"
                if node.type == "method_definition"
                else "function"
            )
            scope_keys[node.id] = entity_key(path, kind, name, node.start_point.row + 1)
        if node.type == "variable_declarator":
            name, value = name_of(node.child_by_field_name("name")), node.child_by_field_name("value")
            if name and value:
                bindings.setdefault((scope_for(node).id, name), []).append((node.start_byte, value))

    def resolve(node: Node, scope: Node, before: int, seen: frozenset[str] = frozenset()) -> Node:
        name = name_of(node)
        if node.type == "identifier" and name not in seen:
            choices = [(pos, value) for pos, value in bindings.get((scope.id, name), []) if pos < before]
            if choices:
                position, value = max(choices, key=lambda item: item[0])
                return resolve(value, scope, position, seen | {name})
        return node

    def dynamic(node: Node) -> bool:
        if node.type in {"string", "number", "true", "false", "null", "undefined"}:
            return False
        if node.type == "template_string":
            return any(n.type == "template_substitution" for n in node.named_children)
        if node.type == "binary_expression":
            return any(dynamic(n) for n in node.named_children)
        return True

    def emit(rule: str, node: Node, basis: str):
        scope = scope_for(node)
        output.detections.append(
            Detection(
                rule,
                path,
                language,
                node.start_point.row + 1,
                node.end_point.row + 1,
                scope_names.get(scope.id, "<module>"),
                basis,
            )
        )

    for node in nodes:
        line, end = node.start_point.row + 1, node.end_point.row + 1
        scope = scope_for(node)
        parent_key = scope_keys.get(scope.id)
        if node.type in SCOPE_TYPES:
            name = scope_names[node.id]
            body = list(walk(node, skip_scopes=True))
            complexity = 1 + sum(n.type in DECISIONS for n in body)
            complexity += sum(
                n.type == "binary_expression"
                and text(n.child_by_field_name("operator")) in {"&&", "||", "??"}
                for n in body
            )
            calls = sorted(
                {name_of(n.child_by_field_name("function")) for n in body if n.type == "call_expression"}
            )[:500]
            features = []
            if any(
                n.type in {"for_statement", "for_in_statement", "while_statement", "do_statement"}
                for n in body
            ):
                features.append("loops")
            if any(n.type == "if_statement" for n in body):
                features.append("conditions")
            if any(n.type == "try_statement" for n in body):
                features.append("exception_handling")
            if node.parent and node.parent.type == "export_statement":
                features.append("exported")
            kind = (
                "class"
                if node.type in {"class", "class_declaration"}
                else "method"
                if node.type == "method_definition"
                else "function"
            )
            output.entities.append(
                Entity(
                    scope_keys[node.id],
                    path,
                    language,
                    kind,
                    name,
                    line,
                    end,
                    parent_key,
                    callees=calls,
                    complexity=complexity,
                    features=features,
                )
            )
            if node.type in FUNCTION_TYPES:
                if complexity > 10:
                    emit(
                        "QUAL-002",
                        node,
                        f"Function complexity is {complexity}; threshold is 10 decision paths.",
                    )
                if end - line + 1 > 80:
                    emit("QUAL-003", node, f"Function spans {end - line + 1} lines; threshold is 80.")
        elif node.type == "import_statement":
            imported = text(node.child_by_field_name("source")).strip("'\"")[:255]
            output.entities.append(
                Entity(
                    entity_key(path, "import", imported, line),
                    path,
                    language,
                    "import",
                    imported,
                    line,
                    end,
                    parent_key,
                    dependencies=[imported],
                )
            )
        elif node.type in {"variable_declarator", "pair"}:
            name = name_of(node.child_by_field_name("name" if node.type == "variable_declarator" else "key"))
            value = node.child_by_field_name("value")
            if name and node.type == "variable_declarator":
                output.entities.append(
                    Entity(
                        entity_key(path, "variable", name, line),
                        path,
                        language,
                        "variable",
                        name,
                        line,
                        end,
                        parent_key,
                    )
                )
            if (
                name
                and SECRET_NAME.search(name)
                and value is not None
                and value.type in {"string", "template_string"}
                and not dynamic(value)
                and len(text(value)) >= 10
            ):
                emit(
                    "SEC-001",
                    node,
                    "Secret-like assignment contains a literal of at least 8 characters; literal value redacted.",
                )
        elif node.type == "catch_clause":
            body = node.child_by_field_name("body")
            if body and not [child for child in body.named_children if child.type != "comment"]:
                emit("QUAL-001", node, "Catch block contains no executable handling statements.")
        elif node.type == "assignment_expression":
            left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
            if name_of(left).endswith((".innerHTML", ".outerHTML")) and right and dynamic(right):
                emit("SEC-010", node, "Dynamic value assigned to an HTML interpretation property.")
        elif node.type == "jsx_attribute":
            if node.named_children and text(node.named_children[0]) == "dangerouslySetInnerHTML":
                emit(
                    "SEC-010", node, "JSX uses dangerouslySetInnerHTML; inspect sanitization and input trust."
                )
        if node.type != "call_expression":
            continue
        function = name_of(node.child_by_field_name("function"))
        arguments = node.child_by_field_name("arguments")
        args = arguments.named_children if arguments else []
        if not args:
            continue
        first = resolve(args[0], scope, node.start_byte)
        if function in {"eval", "Function"} and dynamic(first):
            emit("SEC-004", node, "Dynamic expression reaches JavaScript code evaluation.")
        if (
            function.rsplit(".", 1)[-1] in {"query", "execute"}
            and first.type in {"template_string", "binary_expression"}
            and dynamic(first)
        ):
            emit("SEC-002", node, "Query execution receives a locally constructed dynamic string.")
        if function in {
            "child_process.exec",
            "childProcess.exec",
            "child_process.execSync",
            "childProcess.execSync",
        } and dynamic(first):
            emit("SEC-003", node, "Dynamic command reaches a shell-executing child_process call.")
        if function.endswith(".insertAdjacentHTML") and len(args) > 1 and dynamic(args[1]):
            emit("SEC-010", node, "Dynamic value passed to insertAdjacentHTML.")
    return output
