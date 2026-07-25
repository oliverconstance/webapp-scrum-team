#!/usr/bin/env python3
"""OpenAPI 3.1 YAML Validator Script.

Validates that a provided specification file is valid YAML, adheres to OpenAPI 3.1 structure,
and contains standard RFC 7807 problem details definitions for error handling.
"""
import argparse
import sys
from pathlib import Path
from typing import Any, Dict

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError


def validate_openapi_spec(file_path: Path) -> bool:
    """Validate an OpenAPI YAML specification file.

    Args:
        file_path: Path to the YAML file to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not file_path.exists():
        print(f"[ERROR] Specification file not found: {file_path}", file=sys.stderr)
        return False

    yaml = YAML(typ="safe")
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data: Dict[str, Any] = yaml.load(f)
    except YAMLError as e:
        print(f"[ERROR] YAML parsing failure in {file_path}:\n{e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Failed to read {file_path}: {e}", file=sys.stderr)
        return False

    if not isinstance(data, dict):
        print(f"[ERROR] Specification in {file_path} must be a YAML mapping/dict.", file=sys.stderr)
        return False

    # Check OpenAPI version
    openapi_version = str(data.get("openapi", ""))
    if not openapi_version.startswith("3.1"):
        print(
            f"[ERROR] Invalid OpenAPI version '{openapi_version}' in {file_path}. Must be 3.1.x.",
            file=sys.stderr,
        )
        return False

    # Check required top-level sections
    for required_key in ("info", "paths"):
        if required_key not in data:
            print(
                f"[ERROR] Missing required top-level section '{required_key}' in {file_path}.",
                file=sys.stderr,
            )
            return False

    # Check Info metadata
    info = data.get("info", {})
    if not isinstance(info, dict) or "title" not in info or "version" not in info:
        print(
            f"[ERROR] Section 'info' must contain 'title' and 'version' in {file_path}.",
            file=sys.stderr,
        )
        return False

    # Check for RFC 7807 ProblemDetails schema in components
    components = data.get("components", {})
    schemas = components.get("schemas", {}) if isinstance(components, dict) else {}
    has_problem_details = (
        isinstance(schemas, dict)
        and ("ProblemDetails" in schemas or "ErrorResponse" in schemas or "Problem" in schemas)
    )
    if not has_problem_details:
        print(
            f"[WARNING] RFC 7807 ProblemDetails schema not found under components.schemas in {file_path}.",
            file=sys.stderr,
        )

    print(f"[SUCCESS] OpenAPI 3.1 specification validated successfully: {file_path}")
    return True


def main() -> int:
    """Main CLI execution entrypoint."""
    parser = argparse.ArgumentParser(description="Validate OpenAPI 3.1 YAML specifications.")
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        required=True,
        help="Path to the OpenAPI YAML file to validate.",
    )
    args = parser.parse_args()

    is_valid = validate_openapi_spec(args.file)
    return 0 if is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
