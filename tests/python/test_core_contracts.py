"""NEXUS Core Python Contract Tests."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.nexus_core.config import NexusDaemonConfig
from core.nexus_core.orchestrator import TaskPlan
from core.nexus_core.security import PermissionManager
from sdk.python.nexus_sdk import EngineKind, NexusStatus, PermissionScope, ToolContract
from tools.registry import ToolRegistry


def test_default_config_binds_loopback_only() -> None:
    cfg = NexusDaemonConfig()
    assert cfg.bind_host == "127.0.0.1"
    assert cfg.require_bearer_token is True


def test_permission_manager_blocks_directory_traversal(tmp_path: Path) -> None:
    project_root = tmp_path / "UnityGame"
    project_root.mkdir()
    outside = tmp_path / "secret.txt"
    inside = project_root / "Assets" / "Player.cs"

    pm = PermissionManager()
    assert pm.is_path_within_project(project_root, inside) is True
    assert pm.is_path_within_project(project_root, outside) is False


def test_tool_registry_rejects_unimplemented_planned_tools() -> None:
    registry = ToolRegistry()
    planned = ToolContract(
        id="unity.scene.create",
        category="Scene management",
        description="Planned tool",
        input_schema={},
        output_schema={},
        engine_compatibility=[EngineKind.UNITY],
        required_permissions=[PermissionScope.WRITE_SCENE],
        execution_context="EditorMainThread",
        error_handling="Structured",
        implementation_status=NexusStatus.PLANNED,
    )
    try:
        registry.register(planned)
        assert False, "Expected ValueError for Planned tool"
    except ValueError:
        assert registry.list_tools() == []


def test_task_plan_creates_twelve_steps() -> None:
    plan = TaskPlan.create_template("task-1", "proj-1", "Inspect scene")
    assert len(plan.steps) == 12
    assert plan.steps[4].gate_required is True
