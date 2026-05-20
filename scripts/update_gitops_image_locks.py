from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Helm values with immutable image locks.")
    parser.add_argument("--values-file", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--backend-digest", required=True)
    parser.add_argument("--frontend-digest", required=True)
    parser.add_argument("--nginx-digest", required=True)
    return parser.parse_args()


def apply_image_locks(
    data: dict[str, Any] | None,
    image_tag: str,
    backend_digest: str,
    frontend_digest: str,
    nginx_digest: str,
) -> dict[str, Any]:
    values = data or {}
    component_digests = {
        "backend": backend_digest,
        "worker": backend_digest,
        "frontendAdmin": frontend_digest,
        "nginx": nginx_digest,
    }

    for component, digest in component_digests.items():
        image = values.setdefault(component, {}).setdefault("image", {})
        image["tag"] = image_tag
        image["digest"] = digest

    return values


def update_values_file(
    values_file: str | Path,
    image_tag: str,
    backend_digest: str,
    frontend_digest: str,
    nginx_digest: str,
) -> dict[str, Any]:
    path = Path(values_file)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    updated = apply_image_locks(
        data,
        image_tag=image_tag,
        backend_digest=backend_digest,
        frontend_digest=frontend_digest,
        nginx_digest=nginx_digest,
    )
    path.write_text(yaml.safe_dump(updated, sort_keys=False), encoding="utf-8")
    return updated


def main() -> int:
    args = parse_args()
    update_values_file(
        args.values_file,
        image_tag=args.image_tag,
        backend_digest=args.backend_digest,
        frontend_digest=args.frontend_digest,
        nginx_digest=args.nginx_digest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
