import { describe, expect, it } from 'vitest';
import { DEMO_PROJECTS, DEMO_TASKS } from '../../src/data/demoFixture';
import {
  buildDiagnosticsExportPayload,
  createDraftTaskRecord,
  createInitialAIProviders,
  createInitialEngines,
  createInitialSettings,
  mapDaemonAdapter,
  mapDaemonEngine,
  mapDaemonProject,
  mapDaemonTask,
  mapDaemonToolContract,
} from '../../src/services/controlCenterService';
import { EngineKind, NexusStatus } from '../../sdk/ts';

describe('Control Center Service Layer', () => {
  it('never fabricates Connected engine statuses in initial or demo states', () => {
    const engines = createInitialEngines(DEMO_PROJECTS);
    expect(engines).toHaveLength(2);
    for (const card of engines) {
      expect(card.connectionStatus).toBe(NexusStatus.Disconnected);
      expect(card.verifiedCapabilityCount).toBe(0);
    }

    for (const proj of DEMO_PROJECTS) {
      expect(proj.isDemoFixture).toBe(true);
      expect(proj.status).toBe(NexusStatus.Disconnected);
    }
  });

  it('creates 12-step task plan drafts bound to a registered project', () => {
    const task = createDraftTaskRecord({
      title: 'Audit Player Physics',
      project: DEMO_PROJECTS[0],
    });
    expect(task.steps).toHaveLength(12);
    expect(task.status).toBe(NexusStatus.Planned);
    expect(task.engine).toBe(EngineKind.Unity);
    expect(DEMO_TASKS[0].isDemoFixture).toBe(true);
  });

  it('initializes settings with local-only loopback binding and directory sandboxing', () => {
    const settings = createInitialSettings();
    expect(settings.connections.bindAddress).toBe('127.0.0.1');
    expect(settings.connections.requireBearerToken).toBe(true);
    expect(settings.permissions.projectDirectorySandboxing).toBe(true);
    expect(settings.permissions.allowOutOfProjectWrites).toBe(false);
  });

  it('keeps provider credentials referenced cleanly without raw keys', () => {
    const providers = createInitialAIProviders(null);
    expect(providers.length).toBeGreaterThanOrEqual(4);
    for (const provider of providers) {
      expect(provider.credentialRef).not.toMatch(/sk-|AIza/);
    }
    const exported = buildDiagnosticsExportPayload({ ok: true });
    expect(exported).toContain('NEXUS Desktop & Daemon Control Center');
  });

  it('maps live Python daemon REST payloads into UI domain records accurately', () => {
    const project = mapDaemonProject({
      id: 'proj-1',
      name: 'GodotDemo',
      engine: 'Godot',
      root_path: 'C:/Games/GodotDemo',
      engine_version: '4.3',
      status: 'Connected',
    });
    expect(project.engine).toBe(EngineKind.Godot);
    expect(project.rootPath).toBe('C:/Games/GodotDemo');

    const task = mapDaemonTask(
      {
        id: 'task-1',
        projectId: 'proj-1',
        title: 'Create scene node',
        engine: 'Godot',
        priority: 'high',
        progress: 50,
        status: 'Running',
        currentOperation: 'Executing',
        steps: [
          {
            step_number: 1,
            name: 'Receive',
            subsystem: 'Daemon',
            status: 'Connected',
          },
        ],
        logs: ['Started'],
      },
      [project]
    );
    expect(task.projectName).toBe('GodotDemo');
    expect(task.steps[0].stepNumber).toBe(1);

    const tool = mapDaemonToolContract({
      id: 'nexus.godot.editor.godot.inspect_scene',
      category: 'Scene management',
      description: 'Inspect scene tree',
      engine_compatibility: ['Godot'],
      required_permissions: ['project:read'],
      implementation_status: 'Connected',
    });
    expect(tool.engineCompatibility).toEqual([EngineKind.Godot]);

    const adapter = mapDaemonAdapter({
      adapterId: 'nexus.godot.editor',
      displayName: 'Godot Bridge',
      version: '1.0.0',
      engineKind: 'Godot',
      runtimeLanguage: 'GDScript',
      isTestAdapter: false,
      lifecycleState: 'Connected',
      registeredToolCount: 16,
    });
    expect(adapter.lifecycleState).toBe(NexusStatus.Connected);

    const engineCard = mapDaemonEngine(
      {
        id: 'engine-godot',
        engine: 'Godot',
        display_name: 'Godot Engine 4.x',
        detection_status: 'Available',
        connection_status: 'Connected',
        executable_path: 'C:/Tools/godot4.exe',
        version: '4.3-stable',
        verified_capability_count: 16,
      },
      [project]
    );
    expect(engineCard.availableProjectCount).toBe(1);
    expect(engineCard.verifiedCapabilityCount).toBe(16);
  });
});
