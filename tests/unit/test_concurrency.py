from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from AINDY.db.database import Base
from AINDY.db.models.background_task_lease import BackgroundTaskLease


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


class TestLeaseHeartbeat:
    def test_heartbeat_extends_db_lease_beyond_original_ttl(self, tmp_path):
        from apps.analytics.services import concurrency

        engine = create_engine(
            f"sqlite:///{tmp_path / 'lease_heartbeat.db'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine, tables=[BackgroundTaskLease.__table__])
        session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            bind=engine,
        )

        first_db = session_factory()
        try:
            acquired = concurrency.acquire_execution_lease(
                first_db,
                name="analytics.infinity:test-user:manual",
                owner_id="owner-1",
                ttl_seconds=2,
            )
            first_db.commit()
            assert acquired is True
        finally:
            first_db.close()

        heartbeat = concurrency.LeaseHeartbeat(
            session_factory,
            name="analytics.infinity:test-user:manual",
            owner_id="owner-1",
            ttl_seconds=2,
            interval_seconds=1,
        )
        heartbeat.start()
        try:
            import time

            time.sleep(6)
            competing_db = session_factory()
            try:
                competing = concurrency.acquire_execution_lease(
                    competing_db,
                    name="analytics.infinity:test-user:manual",
                    owner_id="owner-2",
                    ttl_seconds=2,
                )
                assert competing is False
            finally:
                competing_db.close()
        finally:
            heartbeat.stop()
            release_db = session_factory()
            try:
                concurrency.release_execution_lease(
                    release_db,
                    name="analytics.infinity:test-user:manual",
                    owner_id="owner-1",
                )
                release_db.commit()
            finally:
                release_db.close()
                engine.dispose()

    def test_release_execution_lease_unblocks_next_owner_immediately(self, tmp_path):
        from apps.analytics.services import concurrency

        engine = create_engine(
            f"sqlite:///{tmp_path / 'lease_release.db'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine, tables=[BackgroundTaskLease.__table__])
        session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            bind=engine,
        )

        owner_db = session_factory()
        try:
            assert concurrency.acquire_execution_lease(
                owner_db,
                name="analytics.infinity:test-user:manual",
                owner_id="owner-1",
                ttl_seconds=90,
            )
            owner_db.commit()
            concurrency.release_execution_lease(
                owner_db,
                name="analytics.infinity:test-user:manual",
                owner_id="owner-1",
            )
            owner_db.commit()
        finally:
            owner_db.close()

        next_db = session_factory()
        try:
            assert concurrency.acquire_execution_lease(
                next_db,
                name="analytics.infinity:test-user:manual",
                owner_id="owner-2",
                ttl_seconds=90,
            )
        finally:
            next_db.close()
            engine.dispose()
