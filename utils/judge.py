import os
import re

import requests

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _clean(text):
    return _ANSI_RE.sub("", text or "")

PISTON_API_URL = os.getenv("PISTON_URL", "").rstrip("/")

# Free fallback execution engine (Compiler Explorer) used when PISTON_URL is
# not configured. Maps bot language -> (compiler id, input filename, is_compiled).
GODBOLT_URL = os.getenv("GODBOLT_URL", "https://godbolt.org").rstrip("/")
GODBOLT_COMPILERS = {
    "C++": ("g132", "main.cpp", True),
    "Java": ("java1402", "Main.java", True),
    "C#": ("dotnet80csharpmono", "Program.cs", True),
    "Go": ("gccgo142", "main.go", True),
    "Rust": ("r1900", "main.rs", True),
    "Python": ("python314", "main.py", False),
}

LANGUAGE_MAP = {
    "C++": "c++",
    "Python": "python",
    "JavaScript": "javascript",
    "Java": "java",
    "C#": "csharp",
    "Go": "go",
    "Rust": "rust",
}

FALLBACK_VERSIONS = {
    "c++": "10.2.0",
    "python": "3.10.0",
    "javascript": "18.15.0",
    "java": "15.0.2",
    "csharp": "6.12.0",
    "go": "1.16.2",
    "rust": "1.68.2",
}

_FILE_NAMES = {
    "java": "Main.java",
    "csharp": "Program.cs",
}

_runtimes_cache = {}


def _get_versions():
    if _runtimes_cache:
        return _runtimes_cache
    try:
        r = requests.get(f"{PISTON_API_URL}/runtimes", timeout=6)
        if r.ok:
            for rt in r.json():
                _runtimes_cache[rt.get("language")] = rt.get("version")
    except Exception:
        pass
    return _runtimes_cache


def _resolve_version(lang):
    versions = _get_versions()
    return versions.get(lang) or FALLBACK_VERSIONS.get(lang, "*")


def run_code(language, code, stdin, time_limit=2, memory_limit=256, max_code_size=100000):
    if not PISTON_API_URL:
        return run_code_godbolt(language, code, stdin, time_limit, memory_limit, max_code_size)

    lang = LANGUAGE_MAP.get(language)
    if not lang:
        return {"ok": False, "kind": "compile", "error": f"Unsupported language: {language}"}

    if max_code_size and len(code.encode("utf-8")) > max_code_size:
        return {"ok": False, "kind": "compile", "error": "Code exceeds maximum allowed size."}

    files = [{"name": _FILE_NAMES.get(lang, "main"), "content": code}]
    payload = {
        "language": lang,
        "version": _resolve_version(lang),
        "files": files,
        "stdin": stdin or "",
        "run_timeout": max(500, int(time_limit) * 1000),
        "run_memory_limit": max(1024, int(memory_limit) * 1024),
    }

    def _execute(body):
        return requests.post(
            f"{PISTON_API_URL}/execute", json=body, timeout=45
        )

    try:
        r = _execute(payload)
    except Exception as e:
        return {"ok": False, "kind": "runtime", "error": f"Execution engine unreachable: {e}"}

    if not r.ok:
        try:
            retry = _execute({k: v for k, v in payload.items() if k not in ("run_timeout", "run_memory_limit")})
            if retry.ok:
                r = retry
            else:
                return {"ok": False, "kind": "runtime", "error": f"Execution engine error (HTTP {r.status_code}): {r.text[:300]}"}
        except Exception as e:
            return {"ok": False, "kind": "runtime", "error": f"Execution engine error: {e}"}

    data = r.json()
    if data.get("compile") and data["compile"].get("stderr"):
        return {"ok": False, "kind": "compile", "error": (data["compile"]["stderr"] or "Compilation error")[:2000]}
    if data.get("compile") and data["compile"].get("code") not in (None, 0):
        return {"ok": False, "kind": "compile", "error": (data["compile"].get("stderr") or "Compilation error")[:2000]}

    run = data.get("run", {})
    if run.get("timed_out"):
        return {"ok": False, "kind": "timeout", "error": "Time limit exceeded", "stderr": run.get("stderr", "")}
    if run.get("signal") or run.get("code") not in (None, 0):
        return {"ok": False, "kind": "runtime", "error": f"Runtime error (exit {run.get('code')})", "stderr": (run.get("stderr") or "")[:2000]}

    return {"ok": True, "output": run.get("stdout", ""), "stderr": run.get("stderr", "")[:2000]}


def _ce_text(chunks):
    return "".join(c.get("text", "") for c in chunks or [])


def run_code_godbolt(language, code, stdin, time_limit=2, memory_limit=256, max_code_size=100000):
    entry = GODBOLT_COMPILERS.get(language)
    if not entry:
        return {
            "ok": False,
            "kind": "compile",
            "error": (
                f"Language '{language}' needs a Piston instance (set PISTON_URL). "
                f"The free engine covers: {', '.join(sorted(GODBOLT_COMPILERS))}."
            ),
        }
    if max_code_size and len(code.encode("utf-8")) > max_code_size:
        return {"ok": False, "kind": "compile", "error": "Code exceeds maximum allowed size."}

    compiler, filename, is_compiled = entry
    body = {
        "source": code,
        "inputFilename": filename,
        "options": {
            "userArguments": "",
            "executeParameters": {
                "args": [],
                "stdin": stdin or "",
                "compilerOutputBinary": is_compiled,
            },
            "filters": {"execute": True},
        },
    }

    try:
        r = requests.post(
            f"{GODBOLT_URL}/api/compiler/{compiler}/compile",
            json=body,
            headers={"Accept": "application/json"},
            timeout=45,
        )
    except Exception as e:
        return {"ok": False, "kind": "runtime", "error": f"Execution engine unreachable: {e}"}

    if not r.ok:
        return {"ok": False, "kind": "runtime", "error": f"Execution engine error (HTTP {r.status_code}): {r.text[:300]}"}

    data = r.json()
    compile_err = _clean(_ce_text(data.get("stderr")))

    # Compilation failed: no execution result and the engine reports an error.
    if not data.get("execResult"):
        if data.get("code") not in (None, 0) or "error:" in compile_err.lower():
            return {"ok": False, "kind": "compile", "error": compile_err[:2000] or "Compilation error"}
        return {"ok": False, "kind": "runtime", "error": "Execution failed", "stderr": compile_err[:2000]}

    er = data.get("execResult") or {}
    if er.get("code") == 143 or "processing time exceeded" in _clean(_ce_text(er.get("stderr"))).lower():
        return {"ok": False, "kind": "timeout", "error": "Time limit exceeded", "stderr": _clean(_ce_text(er.get("stderr")))[:2000]}
    if er.get("code") not in (None, 0):
        return {
            "ok": False,
            "kind": "runtime",
            "error": f"Runtime error (exit {er.get('code')})",
            "stderr": _clean(_ce_text(er.get("stderr")))[:2000],
        }

    return {
        "ok": True,
        "output": _ce_text(er.get("stdout")),
        "stderr": _clean(_ce_text(er.get("stderr")))[:2000],
    }


def normalize_output(text, ignore_trailing_spaces, ignore_empty_lines, case_sensitive):
    text = text or ""
    lines = text.split("\n")
    if ignore_trailing_spaces:
        lines = [ln.rstrip() for ln in lines]
    if ignore_empty_lines:
        lines = [ln for ln in lines if ln.strip()]
    text = "\n".join(lines).rstrip("\n")
    if not case_sensitive:
        text = text.lower()
    return text


def outputs_match(actual, expected, settings):
    a = normalize_output(
        actual,
        settings.get("ignore_trailing_spaces", False),
        settings.get("ignore_empty_lines", False),
        settings.get("case_sensitive", True),
    )
    e = normalize_output(
        expected,
        settings.get("ignore_trailing_spaces", False),
        settings.get("ignore_empty_lines", False),
        settings.get("case_sensitive", True),
    )
    return a == e
