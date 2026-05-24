from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Helm values with immutable image locks.")
    parser.add_argument("--values-file", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--backend-digest", required=True)
    parser.add_argument("--frontend-digest", required=True)
    parser.add_argument("--nginx-digest", required=True)
    return parser.parse_args()


def validate_image_tag(image_tag: str) -> str:
    normalized = image_tag.strip()
    if not normalized:
        raise ValueError("image tag must not be empty")
    if normalized == "latest":
        raise ValueError("GitOps promotions must not use the mutable latest tag")
    return normalized


def validate_digest(digest: str, label: str) -> str:
    normalized = digest.strip()
    if not _DIGEST_RE.fullmatch(normalized):
        raise ValueError(f"{label} must be an immutable sha256 digest")
    return normalized


def apply_image_locks(
    data: dict[str, Any] | None,
    image_tag: str,
    backend_digest: str,
    frontend_digest: str,
    nginx_digest: str,
) -> dict[str, Any]:
    values = data or {}
    normalized_tag = validate_image_tag(image_tag)
    component_digests = {
        "backend": validate_digest(backend_digest, "backend digest"),
        "worker": validate_digest(backend_digest, "worker digest"),
        "frontendAdmin": validate_digest(frontend_digest, "frontend digest"),
        "nginx": validate_digest(nginx_digest, "nginx digest"),
    }

    for component, digest in component_digests.items():
        image = values.setdefault(component, {}).setdefault("image", {})
        image["tag"] = normalized_tag
        image["digest"] = digest
        image["requireDigest"] = True

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
