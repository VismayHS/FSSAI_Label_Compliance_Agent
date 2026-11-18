"""Regression checks for running the demo from a native, Docker-free workspace."""
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

import run_matrix


class MatrixStartupTests(unittest.TestCase):
    def test_machine_info_when_docker_is_absent(self):
        with patch.object(run_matrix.shutil, "which", return_value=None):
            info = run_matrix.machine_info()
        self.assertIn("python", info)
        self.assertNotIn("docker", info)

    def test_compose_without_docker_has_an_actionable_error(self):
        stderr = StringIO()
        with patch.object(run_matrix.shutil, "which", return_value=None), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as error:
                run_matrix.main(["--compose"])
        self.assertEqual(error.exception.code, 2)
        self.assertIn("Omit --compose", stderr.getvalue())

    def test_compose_commands_run_from_repo_root(self):
        self.assertTrue((run_matrix.ROOT / "docker-compose.yml").is_file())
