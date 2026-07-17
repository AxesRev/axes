"""Tests for application lifespan and startup logic"""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifespan_calls_required_initialization() -> None:
    """Test that lifespan calls all required initialization functions."""
    import aegra_api.main as main_module

    importlib.reload(main_module)
    from aegra_api.main import lifespan

    with (
        patch("aegra_api.main.run_migrations_async", new_callable=AsyncMock) as mock_migrations,
        patch("aegra_api.main.db_manager") as mock_db_manager,
        patch("aegra_api.main.get_langgraph_service") as mock_get_langgraph_service,
        patch("aegra_api.main.event_store") as mock_event_store,
    ):
        mock_db_manager.initialize = AsyncMock()
        mock_db_manager.close = AsyncMock()

        mock_langgraph_service = MagicMock()
        mock_langgraph_service.initialize = AsyncMock()
        mock_get_langgraph_service.return_value = mock_langgraph_service

        mock_event_store.start_cleanup_task = AsyncMock()
        mock_event_store.stop_cleanup_task = AsyncMock()

        mock_app = MagicMock()

        async with lifespan(mock_app):
            pass

        mock_migrations.assert_called_once()
        mock_db_manager.initialize.assert_called_once()
        mock_langgraph_service.initialize.assert_called_once()
        mock_event_store.start_cleanup_task.assert_called_once()

        mock_event_store.stop_cleanup_task.assert_called_once()
        mock_db_manager.close.assert_called_once()
