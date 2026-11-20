import { TOOL_CATEGORY_DEFINITIONS } from '../../tools/categories';
import {
  AIProviderKind,
  AIProviderSpec,
  EngineAdapterCapabilitySpec,
  EnvironmentIncompatibility,
  ExternalMCPClientSpec,
  MCPTransportKind,
  NexusStatus,
  OrchestrationStepSpec,
  SubsystemRecord,
  ToolContractSchema,
} from '../types/nexus';

/**
 * Architectural specification records representing the baseline implementation state
 * of all 17 NEXUS logical components. Live runtime status updates dynamically via daemon probes.
 */
export const ARCHITECTURAL_SUBSYSTEMS: SubsystemRecord[] = [
  {
    id: 'desktop-frontend',
    name: 'Desktop Frontend',
    layer: 'Frontend',
    status: NexusStatus.Available,
    targetRuntime: 'React 19 · TypeScript · Tailwind CSS',
    summary:
      'Control center shell, strict domain contracts, and runtime diagnostics running in browser or Tauri WebView.',
    plannedStage: 'Implemented (Active UI)',
  },
  {
    id: 'desktop-shell',
    name: 'Desktop Shell',
    layer: 'Desktop Shell',
    status: NexusStatus.Available,
    targetRuntime: 'Tauri 2 · Rust · Windows 10/11 64-bit',
    summary:
      'Native window lifecycle, system tray, daemon supervision, and OS credential vault IPC.',
    plannedStage: 'Implemented (Tauri 2 Native)',
  },
  {
    id: 'background-daemon',
    name: 'Background Daemon',
    layer: 'Daemon & Gateway',
    status: NexusStatus.Disconnected,
    targetRuntime: 'Python 3.12+ Service',
    summary: 'Persistent local process coordinating gateways, engine sessions, and task queues.',
    plannedStage: 'Implemented (Local Service)',
  },
  {
    id: 'communication-gateway',
    name: 'Communication Gateway',
    layer: 'Daemon & Gateway',
    status: NexusStatus.Available,
    targetRuntime: '127.0.0.1 Local Multiplexer',
    summary: 'Routes typed commands and events between frontend, MCP clients, and adapters.',
    plannedStage: 'Implemented (Local Daemon)',
  },
  {
    id: 'ai-provider-registry',
    name: 'AI Provider Registry',
    layer: 'AI & Orchestration',
    status: NexusStatus.Available,
    targetRuntime: 'Modular Provider Adapters',
    summary:
      'Manages outbound requests to Gemini, Claude, OpenAI, and custom local/remote endpoints.',
    plannedStage: 'Implemented (Local Daemon)',
  },
  {
    id: 'mcp-server',
    name: 'MCP Server',
    layer: 'Daemon & Gateway',
    status: NexusStatus.Available,
    targetRuntime: 'stdio · Streamable HTTP',
    summary: 'Exposes verified game engine tools to external AI clients with scoped bearer auth.',
    plannedStage: 'Implemented (MCP 2025-03-26)',
  },
  {
    id: 'rest-api',
    name: 'REST API',
    layer: 'Daemon & Gateway',
    status: NexusStatus.Available,
    targetRuntime: 'Loopback HTTP / Express (127.0.0.1)',
    summary:
      'Optional local HTTP control plane for inspection, health checks, and project actions.',
    plannedStage: 'Implemented (Local Daemon)',
  },
  {
    id: 'websocket-service',
    name: 'WebSocket Event Service',
    layer: 'Daemon & Gateway',
    status: NexusStatus.Available,
    targetRuntime: 'Loopback WebSocket Stream',
    summary: 'Streams engine console logs, scene mutations, and task step progress.',
    plannedStage: 'Implemented (Local Daemon)',
  },
  {
    id: 'engine-manager',
    name: 'Engine Manager',
    layer: 'Engine Adapters',
    status: NexusStatus.Available,
    targetRuntime: 'Python Process & Registry Scanner',
    summary:
      'Discovers installed Unity and Godot binaries, verifies versions, and supervises connections.',
    plannedStage: 'Implemented (Local Daemon)',
  },
  {
    id: 'tool-registry',
    name: 'Tool Registry',
    layer: 'Engine Adapters',
    status: NexusStatus.Available,
    targetRuntime: 'Dynamic Schema Catalog',
    summary:
      'Registers verified tools dynamically from active engine adapters with JSON schema validation.',
    plannedStage: 'Implemented (Local Daemon)',
  },
  {
    id: 'universal-adapter-runtime',
    name: 'Universal Adapter Runtime',
    layer: 'Engine Adapters',
    status: NexusStatus.Available,
    targetRuntime: 'Unity C# & Godot GDScript RPC',
    summary: 'Normalizes adapter lifecycle while preserving native Unity and Godot capabilities.',
    plannedStage: 'Implemented (NDJSON JSON-RPC)',
  },
  {
    id: 'project-context-engine',
    name: 'Project Context Engine',
    layer: 'AI & Orchestration',
    status: NexusStatus.Available,
    targetRuntime: 'Project Indexer & AST/Scene Reader',
    summary: 'Maintains live scene hierarchy, script inventory, and compiler diagnostic snapshots.',
    plannedStage: 'Implemented (Local Daemon)',
  },
  {
    id: 'task-orchestrator',
    name: 'Autonomous Task Orchestrator',
    layer: 'AI & Orchestration',
    status: NexusStatus.Available,
    targetRuntime: '16-Phase State Machine',
    summary: 'Plans, checkpoints, executes, diagnoses, repairs, and verifies multi-step dev tasks.',
    plannedStage: 'Implemented (Local Daemon)',
  },
  {
    id: 'permission-manager',
    name: 'Permission Manager',
    layer: 'Security & Storage',
    status: NexusStatus.Available,
    targetRuntime: 'Path Sandbox & Approval Policy',
    summary:
      'Enforces project directory boundaries, destructive-op confirmations, and process rules.',
    plannedStage: 'Implemented (7 Scopes)',
  },
  {
    id: 'storage-manager',
    name: 'Storage Manager',
    layer: 'Security & Storage',
    status: NexusStatus.Available,
    targetRuntime: 'SQLite + OS Credential Vault',
    summary: 'Persists projects, task runs, audit trails, and encrypted credential references.',
    plannedStage: 'Implemented (SQLite)',
  },
  {
    id: 'recovery-manager',
    name: 'Recovery Manager',
    layer: 'Security & Storage',
    status: NexusStatus.Available,
    targetRuntime: 'Snapshot & Rollback Engine',
    summary:
      'Captures pre-task checkpoints and restores project files/scenes selectively on failure.',
    plannedStage: 'Implemented (Local Daemon)',
  },
  {
    id: 'diagnostics-logging',
    name: 'Diagnostics & Logging',
    layer: 'Security & Storage',
    status: NexusStatus.Available,
    targetRuntime: 'Client Probe + Structured JSON Daemon Logs',
    summary:
      'Active runtime probe, secret-redacted JSON daemon logging, and SQLite integrity verification.',
    plannedStage: 'Implemented (Client & Daemon)',
  },
];

export const BUILTIN_AI_PROVIDERS: AIProviderSpec[] = [
  {
    id: 'provider-gemini',
    kind: AIProviderKind.GoogleGemini,
    credentialBackend: 'Server Proxy Env Secret / Windows Credential Vault',
    status: NexusStatus.Available,
    supportsStreaming: true,
    supportsToolCalling: true,
    notes:
      'Server-side route (/api/ai/providers/verify) and Python daemon CredentialStore support.',
  },
  {
    id: 'provider-claude',
    kind: AIProviderKind.AnthropicClaude,
    credentialBackend: 'Windows Credential Vault (Local Daemon)',
    status: NexusStatus.Available,
    supportsStreaming: true,
    supportsToolCalling: true,
    notes: 'Modular adapter in Python bridge. Credentials never stored in browser storage.',
  },
  {
    id: 'provider-openai',
    kind: AIProviderKind.OpenAI,
    credentialBackend: 'Windows Credential Vault (Local Daemon)',
    status: NexusStatus.Available,
    supportsStreaming: true,
    supportsToolCalling: true,
    notes: 'Modular adapter in Python bridge with streaming and tool-calling support.',
  },
  {
    id: 'provider-openai-compat',
    kind: AIProviderKind.OpenAICompatible,
    credentialBackend: 'Optional Bearer / Local Endpoint (Ollama, LM Studio, vLLM)',
    status: NexusStatus.Available,
    supportsStreaming: true,
    supportsToolCalling: true,
    notes: 'Supports local inference servers on 127.0.0.1 without paid cloud API keys.',
  },
  {
    id: 'provider-custom',
    kind: AIProviderKind.Custom,
    credentialBackend: 'Plugin-Defined Provider Adapter',
    status: NexusStatus.Available,
    supportsStreaming: true,
    supportsToolCalling: false,
    notes: 'Extensible provider interface for enterprise or custom routing gateways.',
  },
];

export const EXTERNAL_MCP_CLIENTS: ExternalMCPClientSpec[] = [
  {
    id: 'mcp-stdio-clients',
    name: 'Local CLI & Desktop Agents (Claude Desktop, Cursor, Windsurf)',
    supportedTransports: [MCPTransportKind.Stdio],
    endpointOrCommand: 'python -m core.nexus_core --mcp-stdio',
    authMode: 'OS Process Ownership + Local Project Policy',
    status: NexusStatus.Available,
    notes: 'Spawns NEXUS MCP stdio server directly against the local SQLite registry.',
  },
  {
    id: 'mcp-http-clients',
    name: 'HTTP / SSE Autonomous Agents & IDE Extensions',
    supportedTransports: [MCPTransportKind.StreamableHTTP, MCPTransportKind.SSE],
    endpointOrCommand: 'http://127.0.0.1:47102/mcp',
    authMode: '127.0.0.1 Binding + Per-Install Bearer Token',
    status: NexusStatus.Disconnected,
    notes: 'Accommodates clients lacking stdio support without opening LAN interfaces.',
  },
];

export const ENGINE_ADAPTER_CONTRACT: EngineAdapterCapabilitySpec[] = [
  {
    method: 'detectEngine()',
    description: 'Locate installed editor binaries and validate executable paths.',
    unityMechanism: 'Scan Unity Hub editors.json & Windows Registry',
    godotMechanism: 'Scan PATH, Steam, and user-configured Godot 4.x binaries',
    status: NexusStatus.Available,
  },
  {
    method: 'identifyVersion()',
    description: 'Parse exact engine version, scripting backend, and render pipeline.',
    unityMechanism: 'ProjectSettings/ProjectVersion.txt & Application.unityVersion',
    godotMechanism: 'project.godot config_version & Engine.get_version_info()',
    status: NexusStatus.Available,
  },
  {
    method: 'discoverProjects()',
    description: 'Enumerate valid projects on local Windows drives.',
    unityMechanism: 'Unity Hub projects-v1.json & Assets/ProjectSettings check',
    godotMechanism: 'Recursive scan for project.godot manifests',
    status: NexusStatus.Available,
  },
  {
    method: 'connectProject()',
    description: 'Attach to a running editor plugin or launch editor with bridge enabled.',
    unityMechanism: 'C# EditorPackage loopback TCP/NDJSON handshake',
    godotMechanism: 'GDScript EditorPlugin loopback TCP/NDJSON handshake',
    status: NexusStatus.Available,
  },
  {
    method: 'discoverCapabilities()',
    description: 'Query live editor subsystems, installed packages, and render features.',
    unityMechanism: 'UnityEditor.PackageManager & RenderPipelineAsset inspection',
    godotMechanism: 'ProjectSettings & enabled EditorPlugin registry inspection',
    status: NexusStatus.Available,
  },
  {
    method: 'registerTools()',
    description: 'Publish only verified, currently executable tools to the Tool Registry.',
    unityMechanism: 'Attribute-driven C# tool handler registration',
    godotMechanism: 'GDScript dictionary/schema export from EditorPlugin',
    status: NexusStatus.Available,
  },
  {
    method: 'executeTool()',
    description: 'Dispatch validated JSON arguments onto the editor main thread.',
    unityMechanism: 'EditorApplication.update main-thread queue + Undo.RecordObject',
    godotMechanism: 'Main-thread deferred call + EditorUndoRedoManager',
    status: NexusStatus.Available,
  },
  {
    method: 'inspectProjectState()',
    description: 'Read open scenes, selection, hierarchy, and compile errors.',
    unityMechanism: 'SceneManager.GetActiveScene() & CompilationPipeline',
    godotMechanism: 'EditorInterface.get_edited_scene_root() & ScriptEditor',
    status: NexusStatus.Available,
  },
  {
    method: 'subscribeEvents()',
    description: 'Stream console logs, play-mode transitions, and asset reimports.',
    unityMechanism: 'Application.logMessageReceived & EditorApplication.playModeStateChanged',
    godotMechanism: 'SceneTree signals, EditorFileSystem.filesystem_changed',
    status: NexusStatus.Available,
  },
  {
    method: 'captureScreenshot()',
    description: 'Capture Game View or Scene View frame for visual inspection.',
    unityMechanism: 'ScreenCapture / Camera.Render to RenderTexture PNG',
    godotMechanism: 'SubViewport.get_texture().get_image().save_png()',
    status: NexusStatus.Available,
  },
  {
    method: 'checkHealth()',
    description: 'Verify main-thread responsiveness during asset import or domain reload.',
    unityMechanism: 'Heartbeat ping aware of EditorApplication.isCompiling',
    godotMechanism: 'Heartbeat ping over EditorPlugin _process loop',
    status: NexusStatus.Available,
  },
  {
    method: 'reportError()',
    description: 'Normalize stack traces, file paths, and line numbers into diagnostics.',
    unityMechanism: 'LogType.Error/Exception parser with script asset mapping',
    godotMechanism: 'GDScript runtime & script compilation error hook',
    status: NexusStatus.Available,
  },
  {
    method: 'disconnectAndReconnect()',
    description: 'Survive Unity C# domain reloads and Godot plugin restarts gracefully.',
    unityMechanism: 'AssemblyReloadEvents.beforeAssemblyReload / afterAssemblyReload',
    godotMechanism: '_exit_tree() teardown and backoff reconnect timer',
    status: NexusStatus.Available,
  },
];

export const TOOL_CATEGORY_CONTRACTS: ToolContractSchema[] = TOOL_CATEGORY_DEFINITIONS;

export const ORCHESTRATION_PIPELINE: OrchestrationStepSpec[] = [
  {
    stepNumber: 1,
    name: 'Receive Development Request',
    subsystem: 'Task Orchestrator',
    description: 'Validate user or MCP request structure, target project ID, and constraints.',
    gateRequired: false,
  },
  {
    stepNumber: 2,
    name: 'Inspect Target Project',
    subsystem: 'Project Context Engine',
    description: 'Capture current files, active scenes, scripts, and compiler health.',
    gateRequired: false,
  },
  {
    stepNumber: 3,
    name: 'Resolve Engine & Capabilities',
    subsystem: 'Engine Manager & Tool Registry',
    description: 'Confirm engine adapter connection and query verified executable tools.',
    gateRequired: false,
  },
  {
    stepNumber: 4,
    name: 'Generate Execution Plan',
    subsystem: 'AI Provider / Planner',
    description: 'Produce ordered tool steps bound strictly to registered tool schemas.',
    gateRequired: false,
  },
  {
    stepNumber: 5,
    name: 'Check Permissions & Dependencies',
    subsystem: 'Permission Manager',
    description: 'Verify path sandboxing and prompt user approval for destructive operations.',
    gateRequired: true,
  },
  {
    stepNumber: 6,
    name: 'Create Checkpoint',
    subsystem: 'Recovery Manager',
    description: 'Snapshot target files, scenes, and metadata into SQLite/backup store.',
    gateRequired: false,
  },
  {
    stepNumber: 7,
    name: 'Execute Operations',
    subsystem: 'Universal Adapter Runtime',
    description: 'Dispatch approved steps with support for pause, resume, and cancellation.',
    gateRequired: false,
  },
  {
    stepNumber: 8,
    name: 'Monitor Engine Responses',
    subsystem: 'WebSocket Event Service',
    description: 'Observe editor logs, domain reloads, and asset import completion.',
    gateRequired: false,
  },
  {
    stepNumber: 9,
    name: 'Diagnose Errors',
    subsystem: 'Diagnostics & Logging',
    description: 'Classify compiler, script, or scene hierarchy errors if steps fail.',
    gateRequired: false,
  },
  {
    stepNumber: 10,
    name: 'Attempt Bounded Repairs',
    subsystem: 'Task Orchestrator',
    description: 'Execute bounded repair iterations within retry limits or trigger rollback.',
    gateRequired: true,
  },
  {
    stepNumber: 11,
    name: 'Run Verification',
    subsystem: 'Testing & Validation Tools',
    description: 'Verify actual engine state, test runner output, or play-mode checks.',
    gateRequired: false,
  },
  {
    stepNumber: 12,
    name: 'Produce Completion Report',
    subsystem: 'Storage Manager',
    description: 'Persist verifiable artifacts, diffs, and audit log entry.',
    gateRequired: false,
  },
];

export const ENVIRONMENT_INCOMPATIBILITIES: EnvironmentIncompatibility[] = [
  {
    id: 'inc-tauri-ipc',
    capability: 'Tauri 2 Desktop Shell & Rust IPC',
    windowsDesktopTarget:
      'Native Windows 10/11 64-bit WebView2 host with window.__TAURI_INTERNALS__.',
    aiStudioWebBehavior: 'Sandboxed browser iframe without Tauri runtime.',
    mitigation:
      'BridgeTransport checks runtime host kind and degrades native IPC controls to Unavailable.',
    severity: 'Blocking in Web Preview',
  },
  {
    id: 'inc-python-daemon',
    capability: 'Python 3.12+ Background Daemon',
    windowsDesktopTarget: 'Local daemon spawned by Tauri, bound to 127.0.0.1 with SQLite storage.',
    aiStudioWebBehavior: 'Cloud Linux container cannot spawn local user workstation daemons.',
    mitigation:
      'Frontend performs real loopback probes on demand and displays Disconnected rather than fake telemetry.',
    severity: 'Blocking in Web Preview',
  },
  {
    id: 'inc-engines',
    capability: 'Unity & Godot Editor Processes',
    windowsDesktopTarget: 'Local Unity.exe / Godot.exe running C# and GDScript editor plugins.',
    aiStudioWebBehavior: 'No game engine binaries or local sockets exist in the web sandbox.',
    mitigation:
      'Native engine adapters remain Disconnected with 0 registered live tools until Unity or Godot editor plugins connect.',
    severity: 'Blocking in Web Preview',
  },
  {
    id: 'inc-credentials',
    capability: 'Windows Credential Manager / DPAPI',
    windowsDesktopTarget: 'OS-encrypted secret vault for AI provider keys and local bearer tokens.',
    aiStudioWebBehavior: 'No Windows DPAPI; browser storage is insecure for secrets.',
    mitigation:
      'No API keys are accepted or stored in frontend code/localStorage. Server env proxy handles preview Gemini calls.',
    severity: 'Environment Difference',
  },
  {
    id: 'inc-mixed-content',
    capability: 'HTTPS Iframe to Loopback HTTP/WS',
    windowsDesktopTarget: 'Tauri origin connects directly to 127.0.0.1 REST and WebSocket ports.',
    aiStudioWebBehavior:
      'Remote HTTPS preview origin may block plaintext ws://127.0.0.1 in strict browsers.',
    mitigation:
      'Documented in Diagnostics; export and run locally via Tauri or localhost Vite for daemon attachment.',
    severity: 'Transport Restricted',
  },
];
