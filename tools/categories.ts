import {
  EngineKind,
  NexusStatus,
  PermissionScope,
  ToolCategory,
  ToolContractSchema,
} from '../sdk/ts';

export const TOOL_CATEGORY_DEFINITIONS: ToolContractSchema[] = Object.values(ToolCategory).map(
  (category, idx) => ({
    id: `contract.${category.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`,
    category,
    description: `Contract namespace for ${category.toLowerCase()} capabilities. Live tools register dynamically only when an engine adapter verifies support.`,
    inputSchema: {
      type: 'object',
      properties: {
        projectId: { type: 'string' },
        dryRun: { type: 'boolean', default: false },
      },
      required: ['projectId'],
    },
    outputSchema: {
      type: 'object',
      properties: {
        verified: { type: 'boolean' },
        artifacts: { type: 'array', items: { type: 'string' } },
      },
    },
    engineCompatibility: [EngineKind.Unity, EngineKind.Godot],
    requiredPermissions:
      idx < 2
        ? [PermissionScope.ReadProject]
        : idx === Object.values(ToolCategory).length - 1
          ? [PermissionScope.BuildExport]
          : [PermissionScope.ReadProject, PermissionScope.ExecuteEditorAction],
    executionContext: category === ToolCategory.BuildAndExport ? 'BuildRunner' : 'EditorMainThread',
    errorHandling:
      'Structured diagnostic error with file, line, and checkpoint rollback reference.',
    implementationStatus: NexusStatus.Planned,
  })
);
