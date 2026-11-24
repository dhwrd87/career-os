from __future__ import annotations

import unittest

from careeros.resume import output_filename


class ResumeNamingTests(unittest.TestCase):
    def test_tokenized_name_is_safe_and_deterministic(self):
        pattern = "{public_name} - Resume - {target_role}.pdf"
        first = output_filename(pattern, "Avery / Example", "Support: Coordinator")
        second = output_filename(pattern, "Avery / Example", "Support: Coordinator")
        self.assertEqual(first, second)
        self.assertEqual(first, "Avery Example - Resume - Support Coordinator.pdf")

    def test_candidate_name_is_never_a_package_default(self):
        self.assertEqual(output_filename("{public_name}-{target_role}", "Synthetic Person", "Analyst"), "Synthetic Person-Analyst.pdf")


if __name__ == "__main__":
    unittest.main()
