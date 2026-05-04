from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Helm values with immutable image locks.")
    parser.add_argument("--values-file", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--backend-digest", required=True)
    parser.add_argument("--frontend-digest", required=True)
    parser.add_argument("--nginx-digest", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.values_file)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    component_digests = {
        "backend": args.backend_digest,
        "worker": args.backend_digest,
        "frontendAdmin": args.frontend_digest,
        "nginx": args.nginx_digest,
    }

    for component, digest in component_digests.items():
        image = data.setdefault(component, {}).setdefault("image", {})
        image["tag"] = args.image_tag
        image["digest"] = digest

    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())