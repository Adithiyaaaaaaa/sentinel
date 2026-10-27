"""Versioned, deterministic rule metadata shipped with SENTINEL, never loaded from a target repo."""

from dataclasses import asdict, dataclass

RULESET_VERSION = "2.0.0"
SEVERITY_WEIGHTS = {"critical": 100, "high": 75, "medium": 45, "low": 20}


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str
    category: str
    cwe: str | None
    owasp: str | None
    confidence: float
    verdict: str
    explanation: str
    impact: str
    exploitability: str
    recommendation: str

    def metadata(self) -> dict:
        return asdict(self)

    def risk(self) -> int:
        return round(SEVERITY_WEIGHTS[self.severity] * self.confidence)


RULES = {
    rule.id: rule
    for rule in [
        Rule(
            "SEC-001",
            "Hardcoded secret literal",
            "high",
            "security",
            "CWE-798",
            "A07:2021",
            0.98,
            "confirmed",
            "A secret-like variable is assigned a nonempty literal. The literal is redacted from persisted evidence. Test and demonstration values can also match.",
            "A deployed credential could be recovered from source or version history.",
            "Whether the literal is a live credential is not established.",
            "Load credentials from a protected secret store or environment variable. Rotate the value if it was real and exposed.",
        ),
        Rule(
            "SEC-002",
            "Dynamic SQL reaches an execution call",
            "high",
            "security",
            "CWE-89",
            "A03:2021",
            0.90,
            "likely",
            "A SQL execution call receives a string built with nonliteral interpolation or concatenation. This is a local syntax/dataflow check, not interprocedural taint proof.",
            "Untrusted values could change the meaning of the SQL statement.",
            "Depends on whether interpolated values can be controlled by an attacker.",
            "Use driver-supported bound parameters for values. Validate identifiers against a fixed allowlist; do not interpolate user input.",
        ),
        Rule(
            "SEC-003",
            "Dynamic command passed to a shell",
            "high",
            "security",
            "CWE-78",
            "A03:2021",
            0.92,
            "likely",
            "A nonliteral command reaches a shell execution API or subprocess call with shell=True.",
            "Shell metacharacters could cause unintended command execution.",
            "Requires attacker influence over the command or its interpolated values.",
            "Use a fixed executable with an argument list and shell=False. Validate arguments for the target program.",
        ),
        Rule(
            "SEC-004",
            "Dynamic code evaluation",
            "high",
            "security",
            "CWE-95",
            "A03:2021",
            0.95,
            "likely",
            "A code-evaluation primitive receives a nonliteral expression.",
            "Untrusted text could execute with the application's privileges.",
            "Input provenance and reachability need review.",
            "Replace code evaluation with a data parser or an explicit dispatch table.",
        ),
        Rule(
            "SEC-005",
            "Unsafe deserialization primitive",
            "high",
            "security",
            "CWE-502",
            "A08:2021",
            0.96,
            "possible",
            "An object deserializer capable of constructing executable objects is called. The rule cannot determine the trust of its input.",
            "Untrusted serialized input may execute code or instantiate unsafe objects.",
            "Only exploitable if an attacker can influence serialized input.",
            "Use a data-only format such as JSON and validate its schema. Never unpickle untrusted data; use yaml.safe_load for YAML.",
        ),
        Rule(
            "SEC-006",
            "Weak cryptographic hash",
            "medium",
            "security",
            "CWE-327",
            "A02:2021",
            0.99,
            "confirmed",
            "MD5 or SHA-1 is invoked. The algorithm choice is confirmed; security relevance depends on its use.",
            "Collision resistance is inadequate for security decisions; fast hashes are unsuitable for password storage.",
            "Nonsecurity checksums may be acceptable; inspect the caller's purpose.",
            "Use an appropriate modern hash for integrity, or a dedicated password-hashing algorithm such as Argon2id for passwords.",
        ),
        Rule(
            "SEC-007",
            "Predictable random generator in a token function",
            "medium",
            "security",
            "CWE-338",
            "A02:2021",
            0.86,
            "likely",
            "A noncryptographic random API is used in a function whose name indicates a token, password, nonce, or secret.",
            "Predictable security tokens could be guessed.",
            "The function name supplies context; actual security use still requires review.",
            "Use Python secrets or a platform cryptographic random generator with sufficient entropy.",
        ),
        Rule(
            "SEC-008",
            "Caller-supplied path reaches a file operation",
            "high",
            "security",
            "CWE-22",
            "A01:2021",
            0.73,
            "possible",
            "A function parameter or its local derivative reaches a file API. This conservative rule does not prove that upstream containment checks are absent.",
            "A caller might read or write files outside the intended directory.",
            "Requires untrusted path input and insufficient containment validation.",
            "Resolve against a permitted base, reject filesystem links as needed, and verify the resolved target remains inside the base before access.",
        ),
        Rule(
            "SEC-009",
            "Caller-controlled role check",
            "high",
            "security",
            "CWE-807",
            "A01:2021",
            0.82,
            "likely",
            "An authorization-named function compares an admin role against a header lookup derived from a function parameter.",
            "A spoofed role header could bypass authorization.",
            "A trusted upstream gateway could validate the header; this rule cannot establish that.",
            "Derive authorization from a verified server-side identity and enforce permissions independently of untrusted role headers.",
        ),
        Rule(
            "SEC-010",
            "HTML written through an unsafe sink",
            "high",
            "security",
            "CWE-79",
            "A03:2021",
            0.86,
            "possible",
            "A dynamic value is passed to an HTML interpretation sink. JSX attributes and AST assignments are inspected; plain comments and strings are not.",
            "Untrusted markup could execute scripts in the browser.",
            "Sanitization and input trust are not established by this rule.",
            "Render text through the framework's escaped interpolation or textContent. If HTML is necessary, sanitize with a maintained allowlist-based sanitizer.",
        ),
        Rule(
            "REL-001",
            "Network request has no explicit timeout",
            "medium",
            "reliability",
            "CWE-400",
            None,
            0.85,
            "possible",
            "A recognized requests/httpx call has no timeout keyword. Session defaults or wrappers may supply a timeout outside this local scope.",
            "A stalled peer may consume worker capacity indefinitely.",
            "Depends on transport defaults and the surrounding execution model.",
            "Set explicit connect/read timeouts and handle timeout failures at the appropriate boundary.",
        ),
        Rule(
            "QUAL-001",
            "Exception is silently swallowed",
            "medium",
            "quality",
            "CWE-390",
            None,
            0.98,
            "confirmed",
            "An exception handler is empty or contains only pass/comment statements.",
            "Failures can be hidden and invalid state may be treated as successful.",
            "The intent of the handler requires review.",
            "Handle the specific exception, propagate it, or record an explicit outcome. Document intentionally ignored failures.",
        ),
        Rule(
            "QUAL-002",
            "High cyclomatic complexity",
            "medium",
            "quality",
            None,
            None,
            0.99,
            "confirmed",
            "The function exceeds 10 decision paths in the deterministic complexity metric. Nested function bodies are measured separately.",
            "Many branches make behavior harder to test and change safely.",
            "This is a maintainability signal, not a vulnerability claim.",
            "Split distinct responsibilities, simplify branching, and test each decision path.",
        ),
        Rule(
            "QUAL-003",
            "Long function",
            "low",
            "quality",
            None,
            None,
            0.99,
            "confirmed",
            "A function spans more than 80 physical source lines, including comments and blank lines.",
            "Large functions may combine responsibilities and obscure error paths.",
            "Length alone does not demonstrate a correctness defect.",
            "Extract coherent operations into smaller functions while preserving behavior and tests.",
        ),
        Rule(
            "PERF-001",
            "Database call inside a loop",
            "medium",
            "performance",
            None,
            None,
            0.80,
            "possible",
            "A SQL execution call is syntactically nested within a loop. This is a potential N+1 pattern; batch size and query cost are unknown.",
            "Round trips can grow with the number of loop iterations.",
            "Requires a sufficiently large loop and costly database calls to affect performance.",
            "Consider a join, batched query, or bulk operation. Measure query counts and latency before changing semantics.",
        ),
    ]
}
