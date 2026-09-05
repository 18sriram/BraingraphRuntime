from __future__ import annotations

from pathlib import Path

from app.services.brain_scanner import BrainScanner


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def single(self):
        return self.row

    def consume(self):
        return None


class FakeSession:
    def __init__(self):
        self.file_hash = None
        self.nodes = []
        self.relationships = []
        self.next_id = 1

    def run(self, query, **parameters):
        if "RETURN f.hash" in query:
            return FakeResult(None if self.file_hash is None else {"hash": self.file_hash})
        if "CREATE INDEX" in query:
            return FakeResult()
        if "RETURN elementId(n) AS id" in query:
            node_id = str(self.next_id)
            self.next_id += 1
            self.nodes.append((parameters["node_type"], parameters["name"], parameters.get("path", "")))
            if parameters["node_type"] == "File":
                self.file_hash = parameters["properties"]["hash"]
            return FakeResult({"id": node_id})
        if "RETURN count(r) AS count" in query:
            self.relationships.append((parameters["source_id"], parameters["target_id"]))
            return FakeResult({"count": 1})
        return FakeResult()


class FakeDriver:
    def __init__(self, session):
        self.session_value = session

    def session(self, database):
        return self

    def __enter__(self):
        return self.session_value

    def __exit__(self, *args):
        return False


def test_python_and_typescript_parsers_find_structure(tmp_path: Path) -> None:
    scanner = BrainScanner(None)
    python_nodes, python_imports, python_calls = scanner._parse(Path("main.py"), b"import os\ndef run():\n    helper()\ndef helper():\n    pass\n")
    typescript_nodes, typescript_imports, _ = scanner._parse(
        Path("main.ts"), b"import { value } from './value';\nclass Demo {}\nfunction run() { helper(); }\nfunction helper() {}\n"
    )

    assert python_nodes["functions"] == ["run", "helper"]
    assert python_imports == ["os"]
    assert ("run", "helper") in python_calls
    assert typescript_nodes["classes"] == ["Demo"]
    assert "import { value } from './value';" in typescript_imports
    assert "run" in typescript_nodes["functions"]


def test_scanner_skips_file_with_same_hash(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    file_path.write_text("def run():\n    pass\n", encoding="utf-8")
    session = FakeSession()
    scanner = BrainScanner(FakeDriver(session))

    first = scanner.scan(tmp_path, workspace_id=9)
    second = scanner.scan(tmp_path, workspace_id=9)

    assert first.files_scanned == 1
    assert second.files_skipped == 1
    assert first.files_scanned + second.files_scanned == 1
