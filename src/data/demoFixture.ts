import { EngineKind, NexusStatus, SessionActivityEntry } from '../types/nexus';
import { ORCHESTRATION_PIPELINE } from './architectureSpec';
import { RegisteredProject, TaskRecord } from '../types/nexus';

/**
 * Clearly labeled demonstration fixtures for previewing populated Project Manager,
 * Task Manager, and Activity layouts without fabricating live engine connections.
 */

export const DEMO_PROJECTS: RegisteredProject[] = [
  {
    id: 'demo-proj-unity-rpg',
    name: '[Demo] Emberfall Action Prototype',
    engine: EngineKind.Unity,
    rootPath: 'C:\\Games\\Demo\\EmberfallPrototype',
    engineVersion: '2022.3.42f1',
    status: NexusStatus.Disconnected,
    lastInspectedAt: null,
    activeScene: 'Assets/Scenes/CombatArena.unity',
    notes: 'Demonstration fixture only — not connected to a live Unity Editor instance.',
    isDemoFixture: true,
  },
  {
    id: 'demo-proj-godot-platformer',
    name: '[Demo] Driftline 2D Platformer',
    engine: EngineKind.Godot,
    rootPath: 'C:\\Games\\Demo\\DriftlineGodot',
    engineVersion: '4.3.stable',
    status: NexusStatus.Disconnected,
    lastInspectedAt: null,
    activeScene: 'res://scenes/levels/level_01.tscn',
    notes: 'Demonstration fixture only — not connected to a live Godot Editor instance.',
    isDemoFixture: true,
  },
];

export const DEMO_TASKS: TaskRecord[] = [
  {
    id: 'demo-task-01',
    title: '[Demo] Inspect CombatArena lighting & collider layers',
    projectId: 'demo-proj-unity-rpg',
    projectName: '[Demo] Emberfall Action Prototype',
    engine: EngineKind.Unity,
    status: NexusStatus.Planned,
    currentOperation: 'Awaiting local Python Autonomous Orchestrator & connected Unity adapter',
    createdAt: '2026-11-18T12:00:00.000Z',
    updatedAt: '2026-11-18T12:00:00.000Z',
    checkpointId: 'demo-ckpt-0001',
    steps: ORCHESTRATION_PIPELINE.map((step) => ({
      ...step,
      status: step.stepNumber <= 2 ? NexusStatus.Available : NexusStatus.Planned,
    })),
    logs: [
      '[Demo Fixture] Plan preview generated for visual layout verification.',
      '[Demo Fixture] Steps 05 and 10 require explicit Permission Manager policy approval.',
      '[Demo Fixture] Live execution disabled: no Unity Editor bridge connected.',
    ],
    isDemoFixture: true,
  },
];

export const DEMO_ACTIVITY_ENTRIES: SessionActivityEntry[] = [
  {
    id: 'demo-evt-1',
    timestamp: new Date().toISOString(),
    category: 'Project',
    severity: 'info',
    status: NexusStatus.Unavailable,
    message: '[Demo Fixture] Loaded sample Unity & Godot project manifests for UI inspection.',
    detail: 'Demonstration data is isolated from real bridge telemetry.',
    isDemoFixture: true,
  },
  {
    id: 'demo-evt-2',
    timestamp: new Date().toISOString(),
    category: 'Task',
    severity: 'warning',
    status: NexusStatus.Planned,
    message: '[Demo Fixture] Autonomous task preview paused before execution step.',
    detail: 'Requires running local Python daemon and native Unity or Godot engine adapter.',
    isDemoFixture: true,
  },
];
