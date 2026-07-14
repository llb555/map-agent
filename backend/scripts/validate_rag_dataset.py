"""Validate RAG evaluation datasets and prediction files against JSON Schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator


EVALUATION_ROOT = Path(__file__).resolve().parents[1] / "evaluation"


def validate(instance_path: Path, schema_path: Path) -> list[str]:
    instance = json.loads(instance_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--kind", choices=("dataset", "predictions"), default="dataset")
    args = parser.parse_args()
    schema = EVALUATION_ROOT / f"{args.kind}.schema.json"
    errors = validate(Path(args.path), schema)
    if errors:
        print("\n".join(errors))
        return 2
    print(f"valid:{args.kind}:{args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
