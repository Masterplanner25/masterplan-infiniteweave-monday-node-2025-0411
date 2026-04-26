from __future__ import annotations


def test_learning_models_are_single_canonical_definitions():
    from AINDY.db.models.learning import (
        LearningRecordDB as CanonicalLearningRecordDB,
        LearningThresholdDB as CanonicalLearningThresholdDB,
    )
    from apps.automation.models import (
        LearningRecordDB as AutomationLearningRecordDB,
        LearningThresholdDB as AutomationLearningThresholdDB,
    )

    assert CanonicalLearningRecordDB is AutomationLearningRecordDB
    assert CanonicalLearningThresholdDB is AutomationLearningThresholdDB
    assert (
        CanonicalLearningRecordDB.__table__
        is AutomationLearningRecordDB.__table__
    )
    assert (
        CanonicalLearningThresholdDB.__table__
        is AutomationLearningThresholdDB.__table__
    )
