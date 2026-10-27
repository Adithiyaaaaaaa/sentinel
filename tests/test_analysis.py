"""Positive and negative rule fixtures, syntax extraction, and snapshot integrity."""

import hashlib
from pathlib import Path

import pytest

from backend.analysis.engine import analyze_repository, read_indexed_source
from backend.analysis.indexer import index_repository
from backend.analysis.javascript_parser import parse_javascript
from backend.analysis.python_parser import parse_python
from backend.security.rules import RULES


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("API_KEY = 'synthetic-example-only'", "SEC-001"),
        ("def f(db, x):\n q = f'SELECT * FROM users WHERE id={x}'\n return db.execute(q)", "SEC-002"),
        ("import subprocess as sp\ndef f(command):\n sp.run(command, shell=True)", "SEC-003"),
        ("def f(code):\n return eval(code)", "SEC-004"),
        ("import pickle\ndef f(data):\n return pickle.loads(data)", "SEC-005"),
        ("from hashlib import md5 as digest\ndef f(data):\n return digest(data)", "SEC-006"),
        ("import random\ndef token():\n return random.randint(1, 9999)", "SEC-007"),
        (
            "from pathlib import Path\ndef f(filename):\n return (Path('receipts') / filename).read_text()",
            "SEC-008",
        ),
        ("def is_admin(headers):\n return headers.get('X-Role') == 'admin'", "SEC-009"),
        ("import requests\nrequests.get('https://example.invalid')", "REL-001"),
        ("try:\n x()\nexcept Exception:\n pass", "QUAL-001"),
        ("def f(db, users):\n for user in users:\n  db.execute('SELECT ?', (user,))", "PERF-001"),
    ],
)
def test_python_positive_rules(source, rule):
    result = parse_python("source.py", source)
    assert result.parsed and not result.warnings
    detections = [item for item in result.detections if item.rule_id == rule]
    assert detections
    assert all(1 <= item.line <= item.end_line <= len(source.splitlines()) for item in detections)
    assert all(item.basis for item in detections)


@pytest.mark.parametrize(
    "source",
    [
        "# SECRET = 'comment-only-value'\nexample = \"eval(user_input)\"",
        "import os\nAPI_KEY = os.environ['API_KEY']",
        "def f(db, x):\n return db.execute('SELECT * FROM users WHERE id=?', (x,))",
        "def f(db):\n return db.execute('SELECT ' + '1')",
        "import subprocess\ndef f(arg):\n subprocess.run(['echo', arg], shell=False)",
        "import yaml\nyaml.safe_load('a: b')",
        "import yaml\nyaml.load('a: b', Loader=yaml.SafeLoader)",
        "import hashlib\nhashlib.sha256(b'hello')",
        "import secrets\ndef token():\n return secrets.token_urlsafe(32)",
        "import random\ndef dice():\n return random.randint(1, 6)",
        "def read():\n return open('fixed.txt').read()",
        "import requests\nrequests.get('https://example.invalid', timeout=10)",
        "try:\n x()\nexcept ValueError:\n raise",
    ],
)
def test_python_negative_rules(source):
    result = parse_python("safe.py", source)
    assert result.parsed
    assert result.detections == []


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("const apiKey = 'synthetic-key-example';", "SEC-001"),
        ("function f(db, id) { const q = `SELECT * FROM users WHERE id=${id}`; db.query(q); }", "SEC-002"),
        ("function f(cmd) { child_process.exec(cmd); }", "SEC-003"),
        ("function f(code) { eval(code); }", "SEC-004"),
        ("function f(value) { document.body.innerHTML = value; }", "SEC-010"),
        ("function f(html) { return <div dangerouslySetInnerHTML={{__html:html}}/>; }", "SEC-010"),
        ("try { fail(); } catch(error) { /* ignored */ }", "QUAL-001"),
    ],
)
def test_typescript_positive_rules(source, rule):
    result = parse_javascript("source.tsx", source, "TypeScript")
    assert result.parsed, result.warnings
    assert rule in {item.rule_id for item in result.detections}


@pytest.mark.parametrize(
    "source",
    [
        "// eval(value)\nconst message = 'dangerouslySetInnerHTML';",
        "function f(db, id) { db.query('SELECT * FROM users WHERE id = ?', [id]); }",
        "function f(value) { document.body.textContent = value; return <div>{value}</div>; }",
        "const apiKey = process.env.API_KEY;",
        "try { fail(); } catch (error) { throw error; }",
    ],
)
def test_typescript_negative_rules(source):
    result = parse_javascript("safe.tsx", source, "TypeScript")
    assert result.parsed
    assert not result.detections


def test_entities_structure_and_complexity():
    result = parse_python(
        "module.py",
        "import os\nclass Service:\n def act(self, x):\n  if x:\n   return os.getcwd()\n  return None\n",
    )
    cls = next(item for item in result.entities if item.kind == "class")
    method = next(item for item in result.entities if item.kind == "method")
    assert method.parent == cls.key
    assert method.start_line == 3 and method.end_line == 6
    assert method.complexity == 2 and "os.getcwd" in method.callees
    assert method.features == ["conditions"]
    long = "def long():\n" + " x = 1\n" * 81
    complex_function = "def complex(x):\n" + " if x:\n  return x\n" * 11
    assert "QUAL-003" in {item.rule_id for item in parse_python("long.py", long).detections}
    assert "QUAL-002" in {item.rule_id for item in parse_python("complex.py", complex_function).detections}
    js = parse_javascript(
        "page.tsx",
        "import { foo } from './foo'; export function Page(x: string) { return foo(x); }",
        "TypeScript",
    )
    function = next(item for item in js.entities if item.kind == "function")
    assert function.name == "Page" and function.callees == ["foo"] and "exported" in function.features


def test_invalid_syntax_is_reported_not_silently_certified():
    for result in [
        parse_python("bad.py", "def broken("),
        parse_javascript("bad.ts", "function broken(", "TypeScript"),
    ]:
        assert not result.parsed and result.warnings and not result.detections


def test_analysis_sample_and_evidence_redaction():
    root = Path("examples/sample-repository").resolve()
    result = analyze_repository(root, index_repository(root).files)
    assert result.summary["parsed_files"] == 5
    assert result.summary["finding_count"] == 8
    assert result.summary["failed_files"] == 0
    assert {item.rule_id for item in result.detections} >= {
        "SEC-001",
        "SEC-002",
        "SEC-006",
        "SEC-007",
        "SEC-008",
        "SEC-009",
        "QUAL-001",
        "PERF-001",
    }
    assert "SENTINEL_DEMO_NOT_A_REAL_SECRET" not in str(result)
    assert all(0 <= RULES[item.rule_id].risk() <= 100 for item in result.detections)


def test_source_integrity_and_analysis_coverage(tmp_path):
    path = tmp_path / "source.py"
    path.write_text("def hello():\n return 1\n", encoding="utf-8")
    (tmp_path / "other.go").write_text("package main\n", encoding="utf-8")
    index = index_repository(tmp_path)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert read_indexed_source(tmp_path, "source.py", expected).startswith("def hello")
    with pytest.raises(ValueError):
        read_indexed_source(tmp_path, "../escape.py", expected)
    result = analyze_repository(tmp_path, index.files)
    assert result.summary["parsed_files"] == 1 and result.summary["unsupported_files"] == 1
    path.write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        read_indexed_source(tmp_path, "source.py", expected)
    result = analyze_repository(tmp_path, index.files)
    assert result.summary["failed_files"] == 1 and result.warnings
