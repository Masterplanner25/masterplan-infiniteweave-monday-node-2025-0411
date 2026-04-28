from __future__ import annotations


def test_learning_models_are_single_canonical_definitions():
    from apps.automation.models import (
        LearningRecordDB as AutomationLearningRecordDB,
        LearningThresholdDB as AutomationLearningThresholdDB,
    )
    from apps.automation.public import (
        LearningRecordDB as PublicLearningRecordDB,
        LearningThresholdDB as PublicLearningThresholdDB,
    )

    assert PublicLearningRecordDB is AutomationLearningRecordDB
    assert PublicLearningThresholdDB is AutomationLearningThresholdDB
    assert PublicLearningRecordDB.__table__ is AutomationLearningRecordDB.__table__
    assert PublicLearningThresholdDB.__table__ is AutomationLearningThresholdDB.__table__
