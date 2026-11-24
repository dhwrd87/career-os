from __future__ import annotations

import inspect
import unittest

from careeros.interfaces.compiler import CandidateNeutralCompiler, CareerProfileProvider, CompilerInputV1


class CompilerInterfaceTests(unittest.TestCase):
    def test_input_has_only_generic_components(self) -> None:
        self.assertEqual(
            set(CompilerInputV1.__dataclass_fields__),
            {"profile", "role_family", "target_context", "presentation_policy"},
        )

    def test_profile_provider_is_runtime_checkable_protocol(self) -> None:
        self.assertTrue(getattr(CareerProfileProvider, "_is_runtime_protocol", False))

    def test_compiler_is_runtime_checkable_protocol(self) -> None:
        self.assertTrue(getattr(CandidateNeutralCompiler, "_is_runtime_protocol", False))

    def test_interface_source_has_no_candidate_default(self) -> None:
        source = inspect.getsource(CompilerInputV1)
        self.assertNotIn("default=", source)


if __name__ == "__main__":
    unittest.main()

