from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser
from tree_sitter_typescript import language_tsx, language_typescript


@dataclass
class ScanResult:
    files_scanned: int = 0
    files_skipped: int = 0
    nodes_created: int = 0
    relationships_created: int = 0
    errors: list[str] = field(default_factory=list)


class BrainScanner:
    """Scan source files and persist a workspace graph in Neo4j."""

    SUPPORTED_EXTENSIONS = {".py", ".ts", ".tsx", ".json", ".md"}
    IGNORED_DIRECTORIES = {".git", ".braingraph", ".venv", "node_modules", "__pycache__"}

    def __init__(self, driver: Any, database: str = "neo4j") -> None:
        self.driver = driver
        self.database = database
        self.parsers = {
            ".ts": Parser(Language(language_typescript())),
            ".tsx": Parser(Language(language_tsx())),
        }

    def scan(self, project_path: str | Path, workspace_id: int) -> ScanResult:
        root = Path(project_path).expanduser().resolve()
        result = ScanResult()
        with self.driver.session(database=self.database) as session:
            self._ensure_constraints(session)
            folder_ids: dict[Path, str] = {}
            for folder in self._folders(root):
                folder_ids[folder] = self._merge_folder(session, folder, workspace_id)
            for folder, folder_id in folder_ids.items():
                parent_id = folder_ids.get(folder.parent)
                if parent_id is not None:
                    result.relationships_created += self._merge_relationship(session, parent_id, folder_id, "CONTAINS")
            for path in self._files(root):
                try:
                    self._scan_file(session, path, root, workspace_id, folder_ids, result)
                except (OSError, SyntaxError, UnicodeError, ValueError) as error:
                    result.errors.append(f"{path}: {error}")
        return result

    def _scan_file(self, session: Any, path: Path, root: Path, workspace_id: int, folder_ids: dict[Path, str], result: ScanResult) -> None:
        content = path.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        existing = session.run(
            "MATCH (f:File {path: $path, workspace_id: $workspace_id}) RETURN f.hash AS hash LIMIT 1",
            path=str(path), workspace_id=workspace_id,
        ).single()
        if existing is not None and existing["hash"] == file_hash:
            result.files_skipped += 1
            return
        result.files_scanned += 1
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        language = self._language(path)
        file_id = self._merge_node(session, "File", str(path), {
            "node_type": "File", "name": str(path),
            "path": str(path), "hash": file_hash, "language": language,
            "last_modified": modified, "workspace_id": workspace_id, "archived": False,
        })
        result.nodes_created += 1
        parent_id = folder_ids.get(path.parent)
        if parent_id:
            result.relationships_created += self._merge_relationship(session, parent_id, file_id, "CONTAINS")
        declarations, imports, calls = self._parse(path, content)
        for item_type, names in (("Function", declarations["functions"]), ("Class", declarations["classes"]), ("Import", imports)):
            for name in names:
                node_id = self._merge_node(session, item_type, name, {
                    "node_type": item_type, "name": name, "path": str(path), "workspace_id": workspace_id,
                })
                result.nodes_created += 1
                result.relationships_created += self._merge_relationship(session, file_id, node_id, "DECLARES")
        function_ids = {}
        for name in declarations["functions"]:
            function_ids[name] = self._find_node(session, "Function", name, str(path), workspace_id)
        for caller, callee in calls:
            caller_id = function_ids.get(caller)
            callee_id = function_ids.get(callee)
            if caller_id and callee_id:
                result.relationships_created += self._merge_relationship(session, caller_id, callee_id, "CALLS")
        for name in imports:
            import_id = self._find_node(session, "Import", name, str(path), workspace_id)
            if import_id:
                result.relationships_created += self._merge_relationship(session, file_id, import_id, "IMPORTS")

    def _parse(self, path: Path, content: bytes) -> tuple[dict[str, list[str]], list[str], list[tuple[str, str]]]:
        if path.suffix.lower() == ".py":
            return self._parse_python(content.decode("utf-8"))
        if path.suffix.lower() in {".ts", ".tsx"}:
            return self._parse_typescript(path.suffix.lower(), content)
        return {"functions": [], "classes": []}, [], []

    def _parse_python(self, content: str) -> tuple[dict[str, list[str]], list[str], list[tuple[str, str]]]:
        tree = ast.parse(content)
        functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        calls = []
        for function in [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for call in ast.walk(function):
                if isinstance(call, ast.Call):
                    name = self._call_name(call.func)
                    if name:
                        calls.append((function.name, name))
        return {"functions": functions, "classes": classes}, [name for name in imports if name], calls

    def _parse_typescript(self, extension: str, content: bytes) -> tuple[dict[str, list[str]], list[str], list[tuple[str, str]]]:
        tree = self.parsers[extension].parse(content)
        functions: list[str] = []
        classes: list[str] = []
        imports: list[str] = []
        calls: list[tuple[str, str]] = []
        current_function: list[str] = []

        def visit(node: Any) -> None:
            node_type = node.type
            if node_type in {"function_declaration", "method_definition", "function_expression", "arrow_function"}:
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = name_node.text.decode()
                    functions.append(name)
                    current_function.append(name)
                    for child in node.children:
                        visit(child)
                    current_function.pop()
                    return
            if node_type in {"class_declaration", "abstract_class_declaration"}:
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    classes.append(name_node.text.decode())
            if node_type == "import_statement":
                imports.append(node.text.decode())
            if node_type == "call_expression" and current_function:
                function_node = node.child_by_field_name("function")
                if function_node is not None:
                    calls.append((current_function[-1], function_node.text.decode()))
            for child in node.children:
                visit(child)

        visit(tree.root_node)
        return {"functions": list(dict.fromkeys(functions)), "classes": list(dict.fromkeys(classes))}, list(dict.fromkeys(imports)), calls

    def _merge_node(self, session: Any, node_type: str, name: str, properties: dict[str, Any]) -> str:
        result = session.run(
            "MERGE (n:BrainNode {node_type: $node_type, name: $name, path: $path, workspace_id: $workspace_id}) "
            "SET n += $properties RETURN elementId(n) AS id",
            node_type=node_type, name=name, path=properties.get("path", ""),
            workspace_id=properties["workspace_id"], properties=properties,
        ).single()
        return result["id"]

    def _merge_folder(self, session: Any, path: Path, workspace_id: int) -> str:
        name = path.name or str(path)
        return self._merge_node(session, "Folder", name, {
            "node_type": "Folder", "name": name, "path": str(path), "workspace_id": workspace_id,
        })

    def _find_node(self, session: Any, node_type: str, name: str, path: str, workspace_id: int) -> str | None:
        result = session.run(
            "MATCH (n:BrainNode {node_type: $node_type, name: $name, path: $path, workspace_id: $workspace_id}) "
            "RETURN elementId(n) AS id LIMIT 1", node_type=node_type, name=name, path=path, workspace_id=workspace_id,
        ).single()
        return None if result is None else result["id"]

    def _merge_relationship(self, session: Any, source_id: str, target_id: str, relationship_type: str) -> int:
        result = session.run(
            "MATCH (source) WHERE elementId(source) = $source_id "
            "MATCH (target) WHERE elementId(target) = $target_id "
            f"MERGE (source)-[r:{relationship_type}]->(target) RETURN count(r) AS count",
            source_id=source_id, target_id=target_id,
        ).single()
        return int(result["count"])

    def _ensure_constraints(self, session: Any) -> None:
        session.run("CREATE INDEX brain_node_lookup IF NOT EXISTS FOR (n:BrainNode) ON (n.node_type, n.name, n.path, n.workspace_id)").consume()

    def _files(self, root: Path) -> list[Path]:
        return [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS and not self._ignored(path)]

    def _folders(self, root: Path) -> list[Path]:
        return [root, *[path for path in root.rglob("*") if path.is_dir() and not self._ignored(path)]]

    def _ignored(self, path: Path) -> bool:
        return any(part in self.IGNORED_DIRECTORIES for part in path.parts)

    @staticmethod
    def _language(path: Path) -> str:
        return {".py": "python", ".ts": "typescript", ".tsx": "typescriptreact", ".json": "json", ".md": "markdown"}[path.suffix.lower()]

    @staticmethod
    def _call_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None