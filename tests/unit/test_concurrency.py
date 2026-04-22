from unittest.mock import MagicMock, patch


class TestAcquireExecutionLease:
    def test_acquire_uses_db_when_redis_not_configured(self):
        from apps.analytics.services import concurrency

        db = MagicMock()
        with patch.object(concurrency, "_try_redis_lock", return_value=None) as try_redis:
            with patch.object(concurrency, "_acquire_db_lease", return_value=True) as acquire_db:
                result = concurrency.acquire_execution_lease(
                    db,
                    name="infinity.orchestrator",
                    owner_id="owner-1",
                    ttl_seconds=5,
                )

        assert result is True
        try_redis.assert_called_once_with("infinity.orchestrator", "owner-1", 5)
        acquire_db.assert_called_once_with(
            db,
            name="infinity.orchestrator",
            owner_id="owner-1",
            ttl_seconds=5,
        )

    def test_acquire_uses_redis_when_configured(self):
        from apps.analytics.services import concurrency

        db = MagicMock()
        with patch.object(concurrency, "_try_redis_lock", return_value=True) as try_redis:
            with patch.object(concurrency, "_acquire_db_lease", return_value=False) as acquire_db:
                result = concurrency.acquire_execution_lease(
                    db,
                    name="infinity.orchestrator",
                    owner_id="owner-2",
                    ttl_seconds=5,
                )

        assert result is True
        try_redis.assert_called_once_with("infinity.orchestrator", "owner-2", 5)
        acquire_db.assert_not_called()

    def test_acquire_falls_back_to_db_when_redis_unavailable(self):
        from apps.analytics.services import concurrency

        db = MagicMock()
        with patch.object(concurrency, "_try_redis_lock", return_value=None) as try_redis:
            with patch.object(concurrency, "_acquire_db_lease", return_value=False) as acquire_db:
                result = concurrency.acquire_execution_lease(
                    db,
                    name="infinity.orchestrator",
                    owner_id="owner-3",
                    ttl_seconds=5,
                )

        assert result is False
        try_redis.assert_called_once_with("infinity.orchestrator", "owner-3", 5)
        acquire_db.assert_called_once_with(
            db,
            name="infinity.orchestrator",
            owner_id="owner-3",
            ttl_seconds=5,
        )
