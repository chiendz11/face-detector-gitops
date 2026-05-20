from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.update_gitops_image_locks import apply_image_locks, update_values_file


class ApplyImageLocksTest(unittest.TestCase):
    def test_apply_image_locks_updates_expected_components(self) -> None:
        values = {
            "backend": {"image": {"tag": "old", "digest": "sha256:" + "0" * 64}},
            "worker": {"replicas": 2},
            "frontendAdmin": {"image": {"repository": "ghcr.io/example/admin"}},
            "nginx": {},
            "featureFlags": {"demoMode": True},
        }

        updated = apply_image_locks(
            values,
            image_tag="commit-sha",
            backend_digest="sha256:" + "1" * 64,
            frontend_digest="sha256:" + "2" * 64,
            nginx_digest="sha256:" + "3" * 64,
        )

        self.assertEqual(updated["backend"]["image"]["tag"], "commit-sha")
        self.assertEqual(updated["backend"]["image"]["digest"], "sha256:" + "1" * 64)
        self.assertEqual(updated["worker"]["image"]["tag"], "commit-sha")
        self.assertEqual(updated["worker"]["image"]["digest"], "sha256:" + "1" * 64)
        self.assertEqual(updated["frontendAdmin"]["image"]["tag"], "commit-sha")
        self.assertEqual(updated["frontendAdmin"]["image"]["digest"], "sha256:" + "2" * 64)
        self.assertEqual(updated["nginx"]["image"]["tag"], "commit-sha")
        self.assertEqual(updated["nginx"]["image"]["digest"], "sha256:" + "3" * 64)
        self.assertEqual(updated["featureFlags"], {"demoMode": True})


class UpdateValuesFileTest(unittest.TestCase):
    def test_update_values_file_writes_yaml_with_mutated_locks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values_path = Path(temp_dir) / "values.yaml"
            values_path.write_text("backend:\n  image:\n    repository: ghcr.io/example/backend\n", encoding="utf-8")

            update_values_file(
                values_path,
                image_tag="release-sha",
                backend_digest="sha256:" + "a" * 64,
                frontend_digest="sha256:" + "b" * 64,
                nginx_digest="sha256:" + "c" * 64,
            )

            written = yaml.safe_load(values_path.read_text(encoding="utf-8"))

        self.assertEqual(written["backend"]["image"]["repository"], "ghcr.io/example/backend")
        self.assertEqual(written["backend"]["image"]["tag"], "release-sha")
        self.assertEqual(written["backend"]["image"]["digest"], "sha256:" + "a" * 64)
        self.assertEqual(written["worker"]["image"]["digest"], "sha256:" + "a" * 64)
        self.assertEqual(written["frontendAdmin"]["image"]["digest"], "sha256:" + "b" * 64)
        self.assertEqual(written["nginx"]["image"]["digest"], "sha256:" + "c" * 64)


if __name__ == "__main__":
    unittest.main()
