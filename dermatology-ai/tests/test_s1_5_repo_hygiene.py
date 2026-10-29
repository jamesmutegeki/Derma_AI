"""S1-5 -- the repository can be deployed and checked automatically.

Acceptance criteria
-------------------
1. ``render.yaml`` is a valid blueprint that actually points at this app: python
   runtime, ``rootDir`` set, health check, a persistent disk for SQLite and the
   environment variables the code reads.
2. ``.github/workflows/ci.yml`` runs the test suite and the grep guard on every
   push and pull request.
3. No database, credential file or dataset is committed.
4. Every environment variable the code reads is documented in one place.
"""

from __future__ import annotations

import re

import pytest
import yaml


@pytest.fixture(scope="module")
def blueprint(app_dir):
    return yaml.safe_load((app_dir / "render.yaml").read_text(encoding="utf-8"))


def test_render_blueprint_is_valid(blueprint):
    services = blueprint["services"]
    assert len(services) == 1
    service = services[0]

    assert service["type"] == "web"
    assert service.get("runtime") == "python" or service.get("env") == "python"
    assert service.get("rootDir") == "dermatology-ai", "build must run where requirements.txt lives"
    assert service.get("healthCheckPath") == "/api/health"
    assert "main.py" in service["startCommand"]
    assert "--dashboard" in service["startCommand"]

    env_keys = {item["key"] for item in service.get("envVars", [])}
    for required in ("DATA_DIR", "MODEL_CHECKPOINT_PATH", "ALLOWED_ORIGINS", "TRUST_PROXY"):
        assert required in env_keys, f"{required} must be declared in render.yaml"

    assert service.get("disk"), "SQLite needs a persistent disk or every restart loses patient data"
    assert service["disk"]["mountPath"] == "/var/data"
    data_var = next(item for item in service["envVars"] if item["key"] == "DATA_DIR")
    assert data_var["value"] == "/var/data"


def test_ci_workflow_runs_the_gates(app_dir):
    workflow = (app_dir.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest" in workflow
    assert "ci_grep.sh" in workflow
    assert re.search(r"push:|pull_request:", workflow)
    assert "3.11" in workflow


def test_no_data_or_secrets_are_committed(app_dir, repo_root):
    forbidden = (".db", ".db-wal", ".db-shm", ".pt", ".pth", ".env")
    offenders = [
        str(path.relative_to(repo_root))
        for path in repo_root.rglob("*")
        if path.is_file() and path.suffix in forbidden and ".git/" not in str(path)
    ]
    assert not offenders, f"data/model/secret files committed: {offenders}"


def test_environment_variables_are_documented(app_dir):
    """Every env var read by the code appears in .env.example."""
    pattern = re.compile(r"os\.environ\.get\(\s*[\"']([A-Z0-9_]+)[\"']")
    used = set()
    for path in app_dir.rglob("*.py"):
        if "tests" in path.parts:
            continue
        used.update(pattern.findall(path.read_text(encoding="utf-8", errors="ignore")))

    example = (app_dir / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^([A-Z0-9_]+)=", example, re.M))
    undocumented = used - documented
    assert not undocumented, f"undocumented environment variables: {sorted(undocumented)}"


@pytest.fixture(scope="module")
def repo_root(app_dir):
    return app_dir.parent
