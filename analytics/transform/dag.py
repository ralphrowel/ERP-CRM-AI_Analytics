"""
Transformation Model DAG & Dependency Resolver (Roadmap §V1.2)
Parses SQL model metadata, constructs the execution graph, and resolves
topological order with cycle detection and upstream/downstream tracking.
"""

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SqlModel:
    name: str
    target_table: str
    target_schema: str
    depends_on: list[str] = field(default_factory=list)
    sql_path: Path | None = None
    sql_content: str = ""

    @property
    def full_target_name(self) -> str:
        return (
            f"{self.target_schema}.{self.target_table}"
            if self.target_schema
            else self.target_table
        )


class CyclicDependencyError(Exception):
    pass


class ModelNotFoundError(Exception):
    pass


def parse_model_file(file_path: Path) -> SqlModel:
    """
    Parses metadata comments from a SQL model file.
    Expected headers:
    -- Model: <model_name>
    -- Target: <schema>.<table_name> or <table_name>
    -- Depends on: [<dep1>, <dep2>]
    """
    content = file_path.read_text(encoding="utf-8")
    model_name = file_path.stem
    target_schema = "staging"
    target_table = file_path.stem
    depends_on: list[str] = []

    for line in content.splitlines():
        line_clean = line.strip()
        if not line_clean.startswith("--"):
            continue

        header_line = line_clean.lstrip("-").strip()
        if header_line.lower().startswith("model:"):
            model_name = header_line.split(":", 1)[1].strip()
        elif header_line.lower().startswith("target:"):
            full_target = header_line.split(":", 1)[1].strip()
            if "." in full_target:
                target_schema, target_table = full_target.split(".", 1)
            else:
                target_table = full_target
        elif header_line.lower().startswith("depends on:"):
            raw_deps = header_line.split(":", 1)[1].strip()
            # Parse [dep1, dep2] or comma-separated list
            clean_deps = re.sub(r"[\[\]]", "", raw_deps)
            if clean_deps:
                depends_on = [d.strip() for d in clean_deps.split(",") if d.strip()]

    return SqlModel(
        name=model_name,
        target_table=target_table,
        target_schema=target_schema,
        depends_on=depends_on,
        sql_path=file_path,
        sql_content=content,
    )


class ModelDAG:
    """
    Manages collection of transformation models, dependency ordering,
    and downstream failure cascading.
    """

    def __init__(self, models_dir: Path | None = None):
        if models_dir is None:
            models_dir = Path(__file__).resolve().parent.parent / "models" / "staging"
        self.models_dir = models_dir
        self.models: dict[str, SqlModel] = {}
        self._load_models()

    def _load_models(self) -> None:
        if not self.models_dir.exists():
            return
        for sql_file in sorted(self.models_dir.glob("*.sql")):
            model = parse_model_file(sql_file)
            self.models[model.name] = model

    def get_model(self, name: str) -> SqlModel:
        if name not in self.models:
            raise ModelNotFoundError(f"Model '{name}' not found in {self.models_dir}")
        return self.models[name]

    def get_execution_order(
        self, target_models: list[str] | None = None
    ) -> list[SqlModel]:
        """
        Returns topological ordering of models to execute.
        If target_models is specified, includes the requested models and their upstream prerequisites.
        """
        all_models = self.models
        if not all_models:
            return []

        # Build dependency graph among staging models
        # Note: depends_on may reference 'raw.xyz' or 'staging.stg_xyz' or 'stg_xyz'
        adj: dict[str, set[str]] = defaultdict(set)
        in_degree: dict[str, int] = {name: 0 for name in all_models}

        for name, model in all_models.items():
            for dep in model.depends_on:
                dep_name = dep.split(".")[-1]  # normalize schema prefix
                if dep_name in all_models:
                    adj[dep_name].add(name)
                    in_degree[name] += 1

        # Kahn's algorithm
        queue = deque([name for name, deg in in_degree.items() if deg == 0])
        sorted_names: list[str] = []

        while queue:
            curr = queue.popleft()
            sorted_names.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_names) != len(all_models):
            unresolved = [name for name, deg in in_degree.items() if deg > 0]
            raise CyclicDependencyError(
                f"Cyclic dependency detected among models: {unresolved}"
            )

        if target_models:
            # Filter to target models + all their upstream dependencies
            needed = set()

            def collect_upstream(m_name: str):
                if m_name in needed:
                    return
                needed.add(m_name)
                m = all_models.get(m_name)
                if m:
                    for d in m.depends_on:
                        d_norm = d.split(".")[-1]
                        if d_norm in all_models:
                            collect_upstream(d_norm)

            for target in target_models:
                target_clean = target.split(".")[-1]
                if target_clean not in all_models:
                    raise ModelNotFoundError(f"Model '{target}' not found in registry")
                collect_upstream(target_clean)

            return [all_models[name] for name in sorted_names if name in needed]

        return [all_models[name] for name in sorted_names]

    def get_downstream_dependents(self, failed_model_name: str) -> set[str]:
        """
        Returns set of all model names that transitively depend on failed_model_name.
        Used for failure cascading.
        """
        downstream: set[str] = set()
        queue = deque([failed_model_name])

        while queue:
            curr = queue.popleft()
            for name, model in self.models.items():
                if name in downstream:
                    continue
                for dep in model.depends_on:
                    if dep.split(".")[-1] == curr:
                        downstream.add(name)
                        queue.append(name)
                        break

        return downstream
