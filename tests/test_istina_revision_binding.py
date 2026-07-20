import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.istina_revision_binding import (
    current_git_revision,
    require_current_git_revision,
)


class IstinaRevisionBindingTests(unittest.TestCase):
    @patch("evaluation.istina_revision_binding.current_git_revision")
    def test_exact_repository_head_is_required(self, current_revision):
        current_revision.return_value = "a" * 40

        self.assertEqual(
            require_current_git_revision("A" * 40, Path("repo")),
            "a" * 40,
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            require_current_git_revision("b" * 40, Path("repo"))

    def test_malformed_requested_revision_fails_before_git(self):
        with self.assertRaisesRegex(ValueError, "full 40-hex"):
            require_current_git_revision("abc", Path("repo"))

    def test_git_output_must_itself_be_full_revision(self):
        completed = subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout="abc\n",
            stderr="",
        )
        with patch("subprocess.run", return_value=completed):
            with self.assertRaisesRegex(ValueError, "rev-parse HEAD"):
                current_git_revision(Path("repo"))


if __name__ == "__main__":
    unittest.main()
