"""The pack works alone and offline: no socket in the tests, no network module in the code, no git command
that talks to a remote, no model or API, nothing to install."""
import ast
import json
import socket
import unittest
from pathlib import Path

import tests
from tests import ROOT
from tests.helpers import run

CODE_DIRS = ("coord", "corpus", "eval", "scenarios", "tools")
NETWORK_MODULES = {"socket", "ssl", "urllib", "http", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc",
                   "socketserver", "asyncio", "requests", "httpx", "aiohttp", "webbrowser", "email"}
NOT_STDLIB_HINTS = {"requests", "httpx", "aiohttp", "numpy", "pandas", "yaml", "pytest", "git", "anthropic", "openai"}
REMOTE_VERBS = {"push", "fetch", "pull", "clone", "remote", "ls-remote", "submodule", "send-pack", "fetch-pack", "daemon"}
MODEL_WORDS = ("anthropic", "openai", "api_key", "apikey", "bearer", "claude")


def code_files() -> list[Path]:
    return sorted(p for d in CODE_DIRS for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts)


def imports_of(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add((node.module or "").split(".")[0])
    return names


class Sockets(unittest.TestCase):
    def test_a_socket_cannot_be_opened_while_the_tests_run(self):
        with self.assertRaises(tests.NetworkBlocked):
            socket.socket()
        with self.assertRaises(tests.NetworkBlocked):
            socket.create_connection(("localhost", 9))
        with self.assertRaises(tests.NetworkBlocked):
            socket.getaddrinfo("localhost", 80)


class Code(unittest.TestCase):
    def test_there_is_code_to_scan(self):
        self.assertGreater(len(code_files()), 30)

    def test_no_network_module_is_imported(self):
        for path in code_files():
            with self.subTest(path.relative_to(ROOT).as_posix()):
                self.assertEqual(imports_of(path) & NETWORK_MODULES, set())

    def test_only_the_standard_library_and_the_pack_itself_are_imported(self):
        import sys
        own = {"coord", "corpus", "eval", "scenarios", "tools", "tests", "_common", "stories", "make_inputs"}
        for path in code_files() + sorted((ROOT / "tests").glob("*.py")):
            with self.subTest(path.relative_to(ROOT).as_posix()):
                for name in imports_of(path) - own:
                    self.assertIn(name, sys.stdlib_module_names, f"{name} is not in the standard library")
                    self.assertNotIn(name, NOT_STDLIB_HINTS)

    def test_requirements_file_asks_for_nothing(self):
        lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual([x for x in lines if x.strip() and not x.lstrip().startswith("#")], [])

    def test_no_git_command_that_reaches_a_remote(self):
        """No string constant in the code is one of the git verbs that talk to a remote."""
        for path in code_files():
            with self.subTest(path.relative_to(ROOT).as_posix()):
                found = {n.value for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                         if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in REMOTE_VERBS}
                self.assertEqual(found, set())

    def test_git_is_only_called_through_the_isolated_helper(self):
        """subprocess is used to run git in one place (coord/fixture.py); elsewhere only to run python."""
        callers = [p.relative_to(ROOT).as_posix() for p in code_files() if "subprocess" in imports_of(p)]
        for rel in callers:
            text = (ROOT / rel).read_text(encoding="utf-8")
            if rel != "coord/fixture.py":
                self.assertNotIn('["git"', text, rel)
                self.assertNotIn("'git'", text, rel)
        self.assertIn("coord/fixture.py", callers)

    def test_no_model_and_no_api_in_the_code(self):
        for path in code_files():
            text = path.read_text(encoding="utf-8").lower()
            with self.subTest(path.relative_to(ROOT).as_posix()):
                for word in MODEL_WORDS:
                    self.assertNotIn(word, text)

    def test_nothing_reads_credentials_from_the_environment(self):
        allowed = {"COORD_PACK_WORK", "PATH", "SYSTEMROOT", "SystemRoot", "TEMP", "TMP", "TMPDIR", "PATHEXT", "COMSPEC",
                   "HOME", "USERPROFILE", "LANG", "PYTHONIOENCODING", "PYTHONDONTWRITEBYTECODE"}
        for path in code_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.isupper() \
                        and any(k in node.value for k in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")):
                    self.fail(f"{path.name}: {node.value}")
            self.assertTrue(allowed)


class Scenarios(unittest.TestCase):
    def test_scenario_commands_install_nothing(self):
        for spec in sorted((ROOT / "scenarios").glob("S*/scenario.json")):
            run_cmd = json.loads(spec.read_text(encoding="utf-8"))["run"]
            self.assertEqual(run_cmd, ["python", "check.py"])

    def test_a_scenario_passes_with_sockets_blocked_in_its_own_process(self):
        """Run one check in a fresh interpreter that blocks sockets before anything else is imported."""
        check = ROOT / "scenarios" / "S02_transposed_anchor" / "check.py"
        code, out = run(["-c", "import tests, runpy, sys; sys.argv = [sys.argv[1]]; runpy.run_path(sys.argv[0], run_name='__main__')",
                         check])
        self.assertEqual(code, 0, out)
        self.assertIn("S02_transposed_anchor PASS", out)


class Workflow(unittest.TestCase):
    def test_the_ci_file_installs_nothing_and_uses_no_secret(self):
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for bad in ("pip install", "secrets.", "npm ", "curl ", "wget ", "docker pull"):
            self.assertNotIn(bad, text)
        for must in ("unittest discover", "scenarios/run_all.py", "tools/rebuild.py"):
            self.assertIn(must, text)


if __name__ == "__main__":
    unittest.main()
