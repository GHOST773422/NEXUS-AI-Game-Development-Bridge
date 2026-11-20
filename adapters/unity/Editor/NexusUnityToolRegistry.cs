#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;

namespace Nexus.Bridge.Editor
{
    /// <summary>
    /// Defines verified Unity tool schemas, required NEXUS PermissionScopes, and safe tool dispatch.
    /// </summary>
    public static class NexusUnityToolRegistry
    {
        public static List<NexusToolDescriptor> BuildToolCatalog()
        {
            return new List<NexusToolDescriptor>
            {
                MakeTool("unity.get_editor_state", "Project management", "Inspect Unity compilation, Play Mode, active scene, and build target readiness.", new[] { "project:read" }, ObjSchema()),
                MakeTool("unity.get_scene_hierarchy", "Scene management", "Inspect loaded Unity scene hierarchy recursively with instanceIds, tags, layers, and components.", new[] { "project:read" }, ObjSchema("scenePath", "string", "maxDepth", "integer", "includeInactive", "boolean")),
                MakeTool("unity.inspect_object", "Object management", "Inspect a Unity GameObject transform, components, and SerializedObject properties.", new[] { "project:read" }, ObjSchema("instanceId", "integer", "path", "string")),
                MakeTool("unity.create_object", "Object management", "Create an empty or PrimitiveType GameObject with Undo registration.", new[] { "scene:write" }, ObjSchema("name", "string", "primitiveType", "string", "parentPath", "string")),
                MakeTool("unity.delete_object", "Object management", "Delete a target GameObject from the active Unity scene via Undo.DestroyObjectImmediate.", new[] { "scene:write" }, ObjSchema("instanceId", "integer", "path", "string")),
                MakeTool("unity.transform_object", "Object management", "Update GameObject world or local position, rotation, and scale with Undo.", new[] { "scene:write" }, ObjSchema("instanceId", "integer", "path", "string", "position", "object", "localScale", "object")),
                MakeTool("unity.manage_component", "Component management", "List, add, remove, or update serialized properties on GameObject components.", new[] { "scene:write" }, ObjSchema("action", "string", "componentType", "string", "propertyName", "string")),
                MakeTool("unity.create_script", "Script management", "Create a new C# script strictly under Assets/ and import it into AssetDatabase.", new[] { "script:write" }, ObjSchema("assetPath", "string", "content", "string", "overwrite", "boolean")),
                MakeTool("unity.modify_script", "Script management", "Modify an existing C# script inside Assets/ and trigger AssetDatabase re-import.", new[] { "script:write" }, ObjSchema("assetPath", "string", "content", "string", "searchText", "string", "replaceText", "string")),
                MakeTool("unity.inspect_assets", "Asset management", "Search Unity AssetDatabase by filter and folder with paginated GUIDs and asset types.", new[] { "project:read" }, ObjSchema("filter", "string", "folder", "string", "limit", "integer")),
                MakeTool("unity.import_asset", "Asset management", "Force-import an asset inside Assets/ and verify LoadMainAssetAtPath.", new[] { "assets:modify" }, ObjSchema("assetPath", "string")),
                MakeTool("unity.save_scene", "Scene management", "Save the active Unity scene or all open scenes via EditorSceneManager.", new[] { "scene:write" }, ObjSchema("scenePath", "string", "saveAllOpen", "boolean")),
                MakeTool("unity.get_compilation_status", "Debugging", "Inspect current Unity C# compilation state, assemblies, and compiler errors/warnings.", new[] { "project:read" }, ObjSchema()),
                MakeTool("unity.get_console_logs", "Debugging", "Inspect buffered Unity Console logs captured via logMessageReceivedThreaded.", new[] { "project:read" }, ObjSchema("severity", "string", "limit", "integer", "clear", "boolean")),
                MakeTool("unity.control_play_mode", "Testing", "Enter, exit, pause, resume, or step Unity Editor Play Mode.", new[] { "editor:execute" }, ObjSchema("action", "string")),
                MakeTool("unity.capture_screenshot", "Rendering", "Render SceneView or GameView camera to PNG on the Unity main thread.", new[] { "editor:execute" }, ObjSchema("viewport", "string", "width", "integer", "height", "integer")),
                MakeTool("unity.get_build_status", "Build and export", "Report BuildPipeline state, active build target, enabled scenes, and last BuildReport.", new[] { "project:read" }, ObjSchema())
            };
        }

        public static Dictionary<string, object> DispatchMainThreadTool(
            string toolId,
            string projectId,
            string requestId,
            Dictionary<string, object> arguments
        )
        {
            Dictionary<string, object> args = arguments ?? new Dictionary<string, object>();
            Dictionary<string, object> output;

            switch (toolId)
            {
                case "unity.get_editor_state":
                    output = NexusUnityHandlers.GetEditorState();
                    break;
                case "unity.get_scene_hierarchy":
                    output = NexusUnityHandlers.GetSceneHierarchy(args);
                    break;
                case "unity.inspect_object":
                    output = NexusUnityHandlers.InspectObject(args);
                    break;
                case "unity.create_object":
                    output = NexusUnityHandlers.CreateObject(args);
                    break;
                case "unity.delete_object":
                    output = NexusUnityHandlers.DeleteObject(args);
                    break;
                case "unity.transform_object":
                    output = NexusUnityHandlers.TransformObject(args);
                    break;
                case "unity.manage_component":
                    output = NexusUnityHandlers.ManageComponent(args);
                    break;
                case "unity.create_script":
                    output = NexusUnityHandlers.CreateScript(args);
                    break;
                case "unity.modify_script":
                    output = NexusUnityHandlers.ModifyScript(args);
                    break;
                case "unity.inspect_assets":
                    output = NexusUnityHandlers.InspectAssets(args);
                    break;
                case "unity.import_asset":
                    output = NexusUnityHandlers.ImportAsset(args);
                    break;
                case "unity.save_scene":
                    output = NexusUnityHandlers.SaveScene(args);
                    break;
                case "unity.get_compilation_status":
                    output = NexusUnityStateTracker.GetCompilationSummary();
                    break;
                case "unity.get_console_logs":
                    string sev = args.TryGetValue("severity", out object sObj) ? Convert.ToString(sObj, CultureInfo.InvariantCulture) : string.Empty;
                    int lim = args.TryGetValue("limit", out object lObj) && lObj != null ? Convert.ToInt32(lObj, CultureInfo.InvariantCulture) : 50;
                    bool clr = args.TryGetValue("clear", out object cObj) && cObj != null && Convert.ToBoolean(cObj, CultureInfo.InvariantCulture);
                    output = new Dictionary<string, object>
                    {
                        { "logs", NexusUnityStateTracker.GetConsoleLogs(sev, lim, clr) }
                    };
                    break;
                case "unity.control_play_mode":
                    output = NexusUnityHandlers.ControlPlayMode(args);
                    break;
                case "unity.capture_screenshot":
                    output = NexusUnityHandlers.CaptureScreenshot(args);
                    break;
                case "unity.get_build_status":
                    output = NexusUnityHandlers.GetBuildStatus();
                    break;
                default:
                    throw new NexusRpcException(-32601, "NEXUS_UNKNOWN_UNITY_TOOL", $"Unknown Unity tool '{toolId}'.");
            }

            return new Dictionary<string, object>
            {
                { "requestId", requestId ?? string.Empty },
                { "toolId", toolId },
                { "projectId", projectId ?? string.Empty },
                { "status", "Available" },
                { "verified", true },
                { "isTestAdapter", false },
                { "output", output }
            };
        }

        private static NexusToolDescriptor MakeTool(
            string id,
            string category,
            string description,
            string[] permissions,
            Dictionary<string, object> inputSchema
        )
        {
            return new NexusToolDescriptor
            {
                id = id,
                category = category,
                description = description,
                requiredPermissions = permissions,
                inputSchema = inputSchema,
                outputSchema = new Dictionary<string, object> { { "type", "object" } }
            };
        }

        private static Dictionary<string, object> ObjSchema(params string[] pairs)
        {
            var props = new Dictionary<string, object>();
            for (int i = 0; i + 1 < pairs.Length; i += 2)
            {
                props[pairs[i]] = new Dictionary<string, object> { { "type", pairs[i + 1] } };
            }
            return new Dictionary<string, object>
            {
                { "type", "object" },
                { "properties", props }
            };
        }
    }
}
#endif
