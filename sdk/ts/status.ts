/**
 * NEXUS Shared Status & Taxonomy Enums
 * Single source of truth consumed by the frontend, Node preview backend, and SDK.
 */

export enum NexusStatus {
  Connected = 'Connected',
  Disconnected = 'Disconnected',
  Available = 'Available',
  Unavailable = 'Unavailable',
  Running = 'Running',
  Failed = 'Failed',
  Planned = 'Planned',
}

export enum NavSection {
  Dashboard = 'Dashboard',
  Connections = 'Connections',
  Engines = 'Engines',
  Projects = 'Projects',
  Tools = 'Tools',
  Tasks = 'Tasks',
  Activity = 'Activity',
  Plugins = 'Plugins',
  Diagnostics = 'Diagnostics',
  Settings = 'Settings',
}

export enum EngineKind {
  Unity = 'Unity',
  Godot = 'Godot',
}

export enum AIProviderKind {
  GoogleGemini = 'Google Gemini',
  AnthropicClaude = 'Anthropic Claude',
  OpenAI = 'OpenAI',
  OpenAICompatible = 'OpenAI-Compatible',
  Custom = 'Custom Provider',
}

export enum MCPTransportKind {
  Stdio = 'stdio',
  StreamableHTTP = 'Streamable HTTP',
  SSE = 'SSE',
}

export enum ToolCategory {
  ProjectManagement = 'Project management',
  SceneManagement = 'Scene management',
  ObjectManagement = 'Object management',
  ComponentManagement = 'Component management',
  ScriptManagement = 'Script management',
  AssetManagement = 'Asset management',
  MaterialManagement = 'Material management',
  ShaderManagement = 'Shader management',
  Lighting = 'Lighting',
  Physics = 'Physics',
  Animation = 'Animation',
  Audio = 'Audio',
  UI = 'UI',
  Navigation = 'Navigation',
  Rendering = 'Rendering',
  Debugging = 'Debugging',
  Testing = 'Testing',
  Profiling = 'Profiling',
  BuildAndExport = 'Build and export',
}

export enum PermissionScope {
  ReadProject = 'project:read',
  WriteScene = 'scene:write',
  WriteScript = 'script:write',
  ModifyAssets = 'assets:modify',
  ExecuteEditorAction = 'editor:execute',
  RunTests = 'tests:run',
  BuildExport = 'build:export',
  ProcessSpawnRestricted = 'process:restricted',
}
