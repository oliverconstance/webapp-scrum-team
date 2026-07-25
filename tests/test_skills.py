"""Unit tests for Agent Skills Matrix (.agent/skills/).

Verifies that every skill contains standard YAML frontmatter (`name` and `description`)
conforming to `agentskills.io` and official Google cloud skills repository guidelines, and
tests the OpenAPI specification validator script.
"""

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML


def _load_validate_openapi_spec_func() -> Callable[[Path], bool]:
    """Dynamically load validate_openapi_spec from .agent/ directory."""
    script_path = Path(".agent/skills/openapi-spec-generator/scripts/validate_yaml.py")
    if not script_path.exists():
        raise RuntimeError(f"Validator script not found at {script_path}")

    spec = importlib.util.spec_from_file_location("validate_yaml", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {script_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_yaml"] = module
    spec.loader.exec_module(module)
    return module.validate_openapi_spec


@pytest.mark.unit
def test_skills_frontmatter_existence_and_schema() -> None:
    """Verify all SKILL.md files in .agent/skills/ have valid YAML frontmatter."""
    skills_dir = Path(".agent/skills")
    assert skills_dir.exists(), "Directory .agent/skills/ must exist."

    skill_files = list(skills_dir.glob("*/SKILL.md"))
    assert len(skill_files) >= 5, f"Expected at least 5 SKILL.md files, found {len(skill_files)}."

    yaml = YAML(typ="safe")
    for skill_path in skill_files:
        content = skill_path.read_text(encoding="utf-8")
        assert content.startswith("---"), (
            f"{skill_path} must start with YAML frontmatter delimiter '---'."
        )

        parts = content.split("---", 2)
        assert len(parts) >= 3, (
            f"{skill_path} YAML frontmatter is malformed or missing closing '---'."
        )

        frontmatter_raw = parts[1]
        data: dict[str, Any] = yaml.load(frontmatter_raw)

        assert isinstance(data, dict), f"Frontmatter in {skill_path} must parse to a dictionary."
        assert "name" in data and isinstance(data["name"], str), (
            f"Missing string 'name' in {skill_path}."
        )
        assert "description" in data and isinstance(data["description"], str), (
            f"Missing 'description' in {skill_path}."
        )
        assert len(data["description"].strip()) > 20, (
            f"Description in {skill_path} must be detailed (>20 chars)."
        )


@pytest.mark.unit
def test_openapi_validate_yaml_script(tmp_path: Path) -> None:
    """Test validate_yaml.py against valid and invalid OpenAPI 3.1 specifications."""
    validate_func = _load_validate_openapi_spec_func()

    valid_yaml_path = tmp_path / "valid_spec.yaml"
    valid_yaml_path.write_text(
        """openapi: 3.1.0
info:
  title: Test Service API
  version: 1.0.0
paths:
  /health:
    get:
      summary: Health check endpoint
      responses:
        '200':
          description: OK
components:
  schemas:
    ProblemDetails:
      type: object
      required: [type, title, status]
""",
        encoding="utf-8",
    )

    assert validate_func(valid_yaml_path) is True

    invalid_version_path = tmp_path / "invalid_version.yaml"
    invalid_version_path.write_text(
        """openapi: 3.0.0
info:
  title: Old API
  version: 1.0.0
paths: {}
""",
        encoding="utf-8",
    )
    assert validate_func(invalid_version_path) is False

    missing_paths = tmp_path / "missing_paths.yaml"
    missing_paths.write_text(
        """openapi: 3.1.0
info:
  title: No Paths
  version: 1.0.0
""",
        encoding="utf-8",
    )
    assert validate_func(missing_paths) is False
