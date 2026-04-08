from __future__ import annotations

import unittest

from server.features.learning import auditor_service, code_blame_service, refactoring_choice_service
from server.features.learning import service as learning_mode_handlers
from server.features.learning.policies import (
    AUDITOR_TRAP_COUNT_BY_DIFFICULTY,
    CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY,
    CODE_BLAME_CULPRIT_COUNT_WEIGHTS,
    CODE_BLAME_FACET_TAXONOMY,
    CODE_BLAME_OPTION_IDS,
    MODE_PASS_THRESHOLD,
    REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY,
    REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY,
    REFACTORING_CHOICE_FACET_TAXONOMY,
    REFACTORING_CHOICE_OPTION_IDS,
)


class ModePolicyContractTests(unittest.TestCase):
    def test_pass_threshold_is_shared(self):
        self.assertEqual(learning_mode_handlers.AUDITOR_PASS_THRESHOLD, MODE_PASS_THRESHOLD)
        self.assertEqual(learning_mode_handlers.REFACTORING_CHOICE_PASS_THRESHOLD, MODE_PASS_THRESHOLD)
        self.assertEqual(learning_mode_handlers.CODE_BLAME_PASS_THRESHOLD, MODE_PASS_THRESHOLD)
        self.assertEqual(auditor_service.AUDITOR_PASS_THRESHOLD, MODE_PASS_THRESHOLD)
        self.assertEqual(refactoring_choice_service.REFACTORING_CHOICE_PASS_THRESHOLD, MODE_PASS_THRESHOLD)
        self.assertEqual(code_blame_service.CODE_BLAME_PASS_THRESHOLD, MODE_PASS_THRESHOLD)

    def test_auditor_policy_is_shared(self):
        self.assertEqual(learning_mode_handlers.AUDITOR_TRAP_COUNT_BY_DIFFICULTY, AUDITOR_TRAP_COUNT_BY_DIFFICULTY)

    def test_refactoring_choice_policy_is_shared(self):
        self.assertEqual(learning_mode_handlers.REFACTORING_CHOICE_OPTION_IDS, REFACTORING_CHOICE_OPTION_IDS)
        self.assertEqual(learning_mode_handlers.REFACTORING_CHOICE_FACET_TAXONOMY, REFACTORING_CHOICE_FACET_TAXONOMY)
        self.assertEqual(
            learning_mode_handlers.REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY,
            REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY,
        )
        self.assertEqual(
            learning_mode_handlers.REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY,
            REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY,
        )
        self.assertEqual(refactoring_choice_service.REFACTORING_CHOICE_OPTION_IDS, REFACTORING_CHOICE_OPTION_IDS)
        self.assertEqual(refactoring_choice_service.REFACTORING_CHOICE_FACET_TAXONOMY, REFACTORING_CHOICE_FACET_TAXONOMY)

    def test_code_blame_policy_is_shared(self):
        self.assertEqual(learning_mode_handlers.CODE_BLAME_OPTION_IDS, CODE_BLAME_OPTION_IDS)
        self.assertEqual(learning_mode_handlers.CODE_BLAME_FACET_TAXONOMY, CODE_BLAME_FACET_TAXONOMY)
        self.assertEqual(
            learning_mode_handlers.CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY,
            CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY,
        )
        self.assertEqual(learning_mode_handlers.CODE_BLAME_CULPRIT_COUNT_WEIGHTS, CODE_BLAME_CULPRIT_COUNT_WEIGHTS)
        self.assertEqual(code_blame_service.CODE_BLAME_OPTION_IDS, CODE_BLAME_OPTION_IDS)
        self.assertEqual(code_blame_service.CODE_BLAME_FACET_TAXONOMY, CODE_BLAME_FACET_TAXONOMY)


if __name__ == "__main__":
    unittest.main()

