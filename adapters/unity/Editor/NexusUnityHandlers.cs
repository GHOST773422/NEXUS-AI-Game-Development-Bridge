#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace Nexus.Bridge.Editor
{
    /// <summary>
    /// Executes verified Unity Editor API operations on the Unity Main Editor Thread with strict safety guards.
    /// </summary>
    public static class NexusUnityHandlers
    {
        public static string GetProjectRootPath()
        {
            var dataDir = new DirectoryInfo(Application.dataPath);
            return dataDir.Parent != null ? dataDir.Parent.FullName : dataDir.FullName;
        }

        public static string ComputeProjectId(string projectRootPath)
        {
            string normalized = Path.GetFullPath(projectRootPath)
                .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                .ToLowerInvariant();
            using (SHA256 sha = SHA256.Create())
            {
                byte[] hash = sha.ComputeHash(Encoding.UTF8.GetBytes(normalized));
                var sb = new StringBuilder(12);
                for (int i = 0; i < 6; i++)
                {
                    sb.Append(hash[i].ToString("x2", CultureInfo.InvariantCulture));
                }
                return $"unity-{sb}";
            }
        }

        public static Dictionary<string, object> GetEngineInfo(int listenerPort)
        {
            string rootPath = GetProjectRootPath();
            BuildTarget target = EditorUserBuildSettings.activeBuildTarget;
            BuildTargetGroup targetGroup = BuildPipeline.GetBuildTargetGroup(target);
            ScriptingImplementation backend = PlayerSettings.GetScriptingBackend(targetGroup);
            RenderPipelineAsset pipeline = GraphicsSettings.currentRenderPipeline;

            return new Dictionary<string, object>
            {
                { "adapterId", "nexus.unity.csharp_editor" },
                { "displayName", "Unity C# Editor Bridge Adapter" },
                { "engineKind", "Unity" },
                { "engineVersion", Application.unityVersion },
                { "runtimeLanguage", "C#" },
                { "protocolVersion", "1.0.0" },
                { "isTestAdapter", false },
                { "projectId", ComputeProjectId(rootPath) },
                { "projectName", Application.productName },
                { "companyName", Application.companyName },
                { "projectPath", rootPath },
                { "platform", Application.platform.ToString() },
                { "operatingSystem", SystemInfo.operatingSystem },
                { "activeBuildTarget", target.ToString() },
                { "scriptingBackend", backend.ToString() },
                { "renderPipeline", pipeline != null ? pipeline.GetType().Name : "BuiltInRenderPipeline" },
                { "listenerPort", listenerPort }
            };
        }

        public static Dictionary<string, object> DiscoverProjects(int listenerPort)
        {
            string rootPath = GetProjectRootPath();
            var projects = new List<object>
            {
                new Dictionary<string, object>
                {
                    { "id", ComputeProjectId(rootPath) },
                    { "name", Application.productName },
                    { "engine", "Unity" },
                    { "rootPath", rootPath },
                    { "engineVersion", Application.unityVersion },
                    { "activeScene", SceneManager.GetActiveScene().path },
                    { "listenerPort", listenerPort },
                    { "isActiveEditorSession", true }
                }
            };

            return new Dictionary<string, object>
            {
                { "isTestAdapter", false },
                { "projects", projects }
            };
        }

        public static Dictionary<string, object> GetEditorState()
        {
            Scene activeScene = SceneManager.GetActiveScene();
            bool isCompiling = EditorApplication.isCompiling;
            bool isUpdating = EditorApplication.isUpdating;
            bool isPlaying = EditorApplication.isPlaying;
            bool isTransitioningPlay = EditorApplication.isPlayingOrWillChangePlaymode;

            return new Dictionary<string, object>
            {
                { "projectId", ComputeProjectId(GetProjectRootPath()) },
                { "projectName", Application.productName },
                { "unityVersion", Application.unityVersion },
                { "isCompiling", isCompiling },
                { "isUpdating", isUpdating },
                { "isPlaying", isPlaying },
                { "isPlayingOrWillChangePlaymode", isTransitioningPlay },
                { "isPaused", EditorApplication.isPaused },
                { "isBuildingPlayer", BuildPipeline.isBuildingPlayer },
                { "activeBuildTarget", EditorUserBuildSettings.activeBuildTarget.ToString() },
                { "activeSceneName", activeScene.name },
                { "activeScenePath", activeScene.path },
                { "activeSceneDirty", activeScene.isDirty },
                { "loadedSceneCount", SceneManager.sceneCount },
                { "mainThreadId", NexusMainThreadDispatcher.MainThreadId },
                { "canMutateScene", !isCompiling && !isUpdating },
                { "canWriteScripts", !isCompiling && !isUpdating && !isPlaying },
                { "timestamp", DateTime.UtcNow.ToString("O") }
            };
        }

        public static Dictionary<string, object> GetSceneHierarchy(Dictionary<string, object> args)
        {
            int maxDepth = GetInt(args, "maxDepth", 8);
            bool includeInactive = GetBool(args, "includeInactive", true);
            string sceneFilter = GetString(args, "scenePath", string.Empty);

            var scenes = new List<object>();
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                Scene scene = SceneManager.GetSceneAt(i);
                if (!string.IsNullOrEmpty(sceneFilter) &&
                    !string.Equals(scene.path, sceneFilter, StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(scene.name, sceneFilter, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                var roots = new List<object>();
                if (scene.isLoaded)
                {
                    foreach (GameObject root in scene.GetRootGameObjects())
                    {
                        if (!includeInactive && !root.activeSelf) continue;
                        roots.Add(SerializeHierarchyNode(root, string.Empty, 0, maxDepth, includeInactive));
                    }
                }

                scenes.Add(new Dictionary<string, object>
                {
                    { "name", scene.name },
                    { "path", scene.path },
                    { "isLoaded", scene.isLoaded },
                    { "isDirty", scene.isDirty },
                    { "rootCount", roots.Count },
                    { "roots", roots }
                });
            }

            return new Dictionary<string, object>
            {
                { "activeScene", SceneManager.GetActiveScene().path },
                { "scenes", scenes }
            };
        }

        public static Dictionary<string, object> InspectObject(Dictionary<string, object> args)
        {
            GameObject go = ResolveGameObjectOrThrow(args);
            return SerializeGameObjectDetail(go, includeSerializedProperties: GetBool(args, "includeProperties", true));
        }

        public static Dictionary<string, object> CreateObject(Dictionary<string, object> args)
        {
            GuardSceneMutationAllowed();
            string name = GetString(args, "name", "GameObject");
            string primitiveName = GetString(args, "primitiveType", string.Empty);

            GameObject go;
            if (!string.IsNullOrEmpty(primitiveName))
            {
                if (!Enum.TryParse(primitiveName, ignoreCase: true, out PrimitiveType primitive))
                {
                    throw new NexusRpcException(-32602, "NEXUS_INVALID_PRIMITIVE", $"Unknown PrimitiveType '{primitiveName}'.");
                }
                go = GameObject.CreatePrimitive(primitive);
                go.name = string.IsNullOrEmpty(name) ? primitiveName : name;
            }
            else
            {
                go = new GameObject(name);
            }

            Undo.RegisterCreatedObjectUndo(go, $"NEXUS Create {go.name}");

            GameObject parent = ResolveOptionalParent(args);
            if (parent != null)
            {
                Undo.SetTransformParent(go.transform, parent.transform, "NEXUS Set Parent");
            }

            ApplyTransformVectors(go.transform, args, recordUndo: false);
            MarkSceneDirty(go.scene);

            return new Dictionary<string, object>
            {
                { "created", true },
                { "gameObject", SerializeGameObjectDetail(go, includeSerializedProperties: false) }
            };
        }

        public static Dictionary<string, object> DeleteObject(Dictionary<string, object> args)
        {
            GuardSceneMutationAllowed();
            GameObject go = ResolveGameObjectOrThrow(args);
            int deletedId = go.GetInstanceID();
            string deletedPath = GetHierarchyPath(go.transform);
            Scene scene = go.scene;

            Undo.DestroyObjectImmediate(go);
            MarkSceneDirty(scene);

            return new Dictionary<string, object>
            {
                { "deleted", true },
                { "instanceId", deletedId },
                { "hierarchyPath", deletedPath }
            };
        }

        public static Dictionary<string, object> TransformObject(Dictionary<string, object> args)
        {
            GuardSceneMutationAllowed();
            GameObject go = ResolveGameObjectOrThrow(args);
            ApplyTransformVectors(go.transform, args, recordUndo: true);
            MarkSceneDirty(go.scene);

            return new Dictionary<string, object>
            {
                { "transformed", true },
                { "instanceId", go.GetInstanceID() },
                { "hierarchyPath", GetHierarchyPath(go.transform) },
                { "transform", SerializeTransform(go.transform) }
            };
        }

        public static Dictionary<string, object> ManageComponent(Dictionary<string, object> args)
        {
            GameObject go = ResolveGameObjectOrThrow(args);
            string action = GetString(args, "action", "list").Trim().ToLowerInvariant();
            string typeName = GetString(args, "componentType", string.Empty);

            if (action == "list")
            {
                return new Dictionary<string, object>
                {
                    { "instanceId", go.GetInstanceID() },
                    { "components", SerializeComponents(go, includeProperties: true) }
                };
            }

            GuardSceneMutationAllowed();
            if (string.IsNullOrEmpty(typeName))
            {
                throw new NexusRpcException(-32602, "NEXUS_MISSING_COMPONENT_TYPE", "componentType is required.");
            }

            Type componentType = ResolveComponentType(typeName);
            if (componentType == null)
            {
                throw new NexusRpcException(-32602, "NEXUS_UNKNOWN_COMPONENT_TYPE", $"Component type '{typeName}' was not found.");
            }

            if (action == "add")
            {
                Component added = Undo.AddComponent(go, componentType);
                if (added == null)
                {
                    throw new NexusRpcException(-32005, "NEXUS_COMPONENT_ADD_FAILED", $"Unity rejected adding '{componentType.FullName}' to '{go.name}'.");
                }
                MarkSceneDirty(go.scene);
                return new Dictionary<string, object>
                {
                    { "added", true },
                    { "componentType", added.GetType().FullName },
                    { "componentInstanceId", added.GetInstanceID() }
                };
            }

            Component existing = go.GetComponent(componentType);
            if (existing == null)
            {
                throw new NexusRpcException(-32602, "NEXUS_COMPONENT_NOT_FOUND", $"'{go.name}' does not have component '{componentType.FullName}'.");
            }

            if (action == "remove")
            {
                if (existing is Transform)
                {
                    throw new NexusRpcException(-32602, "NEXUS_CANNOT_REMOVE_TRANSFORM", "Transform component cannot be removed from a GameObject.");
                }
                string removedType = existing.GetType().FullName;
                Undo.DestroyObjectImmediate(existing);
                MarkSceneDirty(go.scene);
                return new Dictionary<string, object>
                {
                    { "removed", true },
                    { "componentType", removedType }
                };
            }

            if (action == "set_property")
            {
                string propName = GetString(args, "propertyName", string.Empty);
                if (string.IsNullOrEmpty(propName))
                {
                    throw new NexusRpcException(-32602, "NEXUS_MISSING_PROPERTY_NAME", "propertyName is required for set_property.");
                }
                if (!args.TryGetValue("value", out object rawValue))
                {
                    throw new NexusRpcException(-32602, "NEXUS_MISSING_PROPERTY_VALUE", "value is required for set_property.");
                }

                var serialized = new SerializedObject(existing);
                SerializedProperty prop = serialized.FindProperty(propName);
                if (prop == null)
                {
                    throw new NexusRpcException(-32602, "NEXUS_PROPERTY_NOT_FOUND", $"SerializedProperty '{propName}' not found on '{componentType.Name}'.");
                }

                Undo.RecordObject(existing, $"NEXUS Set {componentType.Name}.{propName}");
                ApplySerializedPropertyValue(prop, rawValue);
                serialized.ApplyModifiedProperties();
                MarkSceneDirty(go.scene);

                return new Dictionary<string, object>
                {
                    { "updated", true },
                    { "componentType", componentType.FullName },
                    { "propertyName", propName },
                    { "propertyType", prop.propertyType.ToString() }
                };
            }

            throw new NexusRpcException(-32602, "NEXUS_INVALID_ACTION", $"Unsupported manage_component action '{action}'.");
        }

        public static Dictionary<string, object> CreateScript(Dictionary<string, object> args)
        {
            GuardScriptMutationAllowed();
            string assetPath = NormalizeProjectAssetPath(GetString(args, "assetPath", string.Empty), requireCSharp: true);
            string content = GetString(args, "content", string.Empty);
            bool overwrite = GetBool(args, "overwrite", false);

            if (string.IsNullOrWhiteSpace(content))
            {
                throw new NexusRpcException(-32602, "NEXUS_EMPTY_SCRIPT", "Script content cannot be empty.");
            }

            string absPath = ToAbsoluteProjectPath(assetPath);
            if (File.Exists(absPath) && !overwrite)
            {
                throw new NexusRpcException(-32004, "NEXUS_SCRIPT_EXISTS", $"Script '{assetPath}' already exists (pass overwrite=true to replace).");
            }

            string dir = Path.GetDirectoryName(absPath);
            if (!string.IsNullOrEmpty(dir))
            {
                Directory.CreateDirectory(dir);
            }

            File.WriteAllText(absPath, content, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
            AssetDatabase.ImportAsset(assetPath, ImportAssetOptions.ForceUpdate);

            return new Dictionary<string, object>
            {
                { "created", true },
                { "assetPath", assetPath },
                { "guid", AssetDatabase.AssetPathToGUID(assetPath) },
                { "isCompiling", EditorApplication.isCompiling }
            };
        }

        public static Dictionary<string, object> ModifyScript(Dictionary<string, object> args)
        {
            GuardScriptMutationAllowed();
            string assetPath = NormalizeProjectAssetPath(GetString(args, "assetPath", string.Empty), requireCSharp: true);
            string absPath = ToAbsoluteProjectPath(assetPath);

            if (!File.Exists(absPath))
            {
                throw new NexusRpcException(-32602, "NEXUS_SCRIPT_NOT_FOUND", $"Script '{assetPath}' does not exist.");
            }

            string newContent;
            if (args.TryGetValue("content", out object fullContentObj) && fullContentObj != null)
            {
                newContent = Convert.ToString(fullContentObj, CultureInfo.InvariantCulture) ?? string.Empty;
            }
            else
            {
                string searchText = GetString(args, "searchText", string.Empty);
                string replaceText = GetString(args, "replaceText", string.Empty);
                if (string.IsNullOrEmpty(searchText))
                {
                    throw new NexusRpcException(-32602, "NEXUS_MISSING_EDIT", "Provide either 'content' or non-empty 'searchText' and 'replaceText'.");
                }
                string existing = File.ReadAllText(absPath, Encoding.UTF8);
                if (!existing.Contains(searchText, StringComparison.Ordinal))
                {
                    throw new NexusRpcException(-32602, "NEXUS_SEARCH_TEXT_NOT_FOUND", $"'{searchText}' was not found inside '{assetPath}'.");
                }
                newContent = existing.Replace(searchText, replaceText, StringComparison.Ordinal);
            }

            File.WriteAllText(absPath, newContent, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
            AssetDatabase.ImportAsset(assetPath, ImportAssetOptions.ForceUpdate);

            return new Dictionary<string, object>
            {
                { "modified", true },
                { "assetPath", assetPath },
                { "guid", AssetDatabase.AssetPathToGUID(assetPath) },
                { "isCompiling", EditorApplication.isCompiling }
            };
        }

        public static Dictionary<string, object> InspectAssets(Dictionary<string, object> args)
        {
            string filter = GetString(args, "filter", string.Empty);
            string folder = GetString(args, "folder", "Assets");
            int limit = Math.Clamp(GetInt(args, "limit", 100), 1, 500);
            int offset = Math.Max(0, GetInt(args, "offset", 0));

            string normalizedFolder = NormalizeProjectAssetPath(folder, requireCSharp: false, allowFolder: true);
            string[] guids = AssetDatabase.FindAssets(filter, new[] { normalizedFolder });

            var items = new List<object>();
            int end = Math.Min(guids.Length, offset + limit);
            for (int i = offset; i < end; i++)
            {
                string guid = guids[i];
                string path = AssetDatabase.GUIDToAssetPath(guid);
                Type mainType = AssetDatabase.GetMainAssetTypeAtPath(path);
                items.Add(new Dictionary<string, object>
                {
                    { "guid", guid },
                    { "path", path },
                    { "type", mainType != null ? mainType.FullName : "Unknown" },
                    { "isFolder", AssetDatabase.IsValidFolder(path) }
                });
            }

            return new Dictionary<string, object>
            {
                { "folder", normalizedFolder },
                { "totalCount", guids.Length },
                { "offset", offset },
                { "limit", limit },
                { "assets", items }
            };
        }

        public static Dictionary<string, object> ImportAsset(Dictionary<string, object> args)
        {
            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                throw new NexusRpcException(-32001, "NEXUS_EDITOR_BUSY", "Cannot import assets while Unity Editor is compiling or updating.");
            }

            string assetPath = NormalizeProjectAssetPath(GetString(args, "assetPath", string.Empty), requireCSharp: false);
            string absPath = ToAbsoluteProjectPath(assetPath);
            if (!File.Exists(absPath) && !Directory.Exists(absPath))
            {
                throw new NexusRpcException(-32602, "NEXUS_ASSET_NOT_FOUND", $"Asset '{assetPath}' does not exist on disk.");
            }

            AssetDatabase.ImportAsset(assetPath, ImportAssetOptions.ForceUpdate);
            UnityEngine.Object loaded = AssetDatabase.LoadMainAssetAtPath(assetPath);

            return new Dictionary<string, object>
            {
                { "imported", true },
                { "assetPath", assetPath },
                { "guid", AssetDatabase.AssetPathToGUID(assetPath) },
                { "loadedMainAsset", loaded != null },
                { "assetType", loaded != null ? loaded.GetType().FullName : "Unknown" }
            };
        }

        public static Dictionary<string, object> SaveScene(Dictionary<string, object> args)
        {
            if (EditorApplication.isCompiling)
            {
                throw new NexusRpcException(-32001, "NEXUS_EDITOR_COMPILING", "Cannot save scenes while Unity is compiling scripts.");
            }
            if (EditorApplication.isPlaying)
            {
                throw new NexusRpcException(-32001, "NEXUS_PLAYMODE_ACTIVE", "Cannot save scenes directly while Unity is in Play Mode.");
            }

            string targetPath = GetString(args, "scenePath", string.Empty);
            bool saveAllOpen = GetBool(args, "saveAllOpen", false);

            if (saveAllOpen)
            {
                bool ok = EditorSceneManager.SaveOpenScenes();
                return new Dictionary<string, object>
                {
                    { "saved", ok },
                    { "saveAllOpen", true },
                    { "activeScenePath", SceneManager.GetActiveScene().path },
                    { "activeSceneDirty", SceneManager.GetActiveScene().isDirty }
                };
            }

            Scene active = SceneManager.GetActiveScene();
            string saveAsPath = string.IsNullOrEmpty(targetPath)
                ? active.path
                : NormalizeProjectAssetPath(targetPath, requireCSharp: false);

            if (string.IsNullOrEmpty(saveAsPath))
            {
                throw new NexusRpcException(-32602, "NEXUS_UNTITLED_SCENE", "Active scene has no path; provide 'scenePath' under Assets/ ending with .unity.");
            }

            bool saved = EditorSceneManager.SaveScene(active, saveAsPath);
            return new Dictionary<string, object>
            {
                { "saved", saved },
                { "scenePath", active.path },
                { "sceneName", active.name },
                { "isDirty", active.isDirty }
            };
        }

        public static Dictionary<string, object> ControlPlayMode(Dictionary<string, object> args)
        {
            string action = GetString(args, "action", string.Empty).Trim().ToLowerInvariant();
            switch (action)
            {
                case "enter":
                    if (EditorApplication.isCompiling || EditorApplication.isUpdating)
                    {
                        throw new NexusRpcException(-32001, "NEXUS_EDITOR_COMPILING", "Cannot enter Play Mode while scripts are compiling or assets are updating.");
                    }
                    EditorApplication.isPlaying = true;
                    break;
                case "exit":
                    EditorApplication.isPlaying = false;
                    break;
                case "pause":
                    EditorApplication.isPaused = true;
                    break;
                case "resume":
                    EditorApplication.isPaused = false;
                    break;
                case "step":
                    if (!EditorApplication.isPlaying)
                    {
                        throw new NexusRpcException(-32001, "NEXUS_NOT_IN_PLAYMODE", "EditorApplication.Step() requires Play Mode to be active.");
                    }
                    EditorApplication.Step();
                    break;
                default:
                    throw new NexusRpcException(-32602, "NEXUS_INVALID_ACTION", $"Unsupported Play Mode action '{action}'. Expected enter, exit, pause, resume, or step.");
            }

            return new Dictionary<string, object>
            {
                { "action", action },
                { "isPlaying", EditorApplication.isPlaying },
                { "isPlayingOrWillChangePlaymode", EditorApplication.isPlayingOrWillChangePlaymode },
                { "isPaused", EditorApplication.isPaused }
            };
        }

        public static Dictionary<string, object> CaptureScreenshot(Dictionary<string, object> args)
        {
            string viewport = GetString(args, "viewport", "SceneView");
            int width = Math.Clamp(GetInt(args, "width", 1280), 64, 3840);
            int height = Math.Clamp(GetInt(args, "height", 720), 64, 2160);
            string projectId = ComputeProjectId(GetProjectRootPath());

            Camera cam = null;
            if (string.Equals(viewport, "SceneView", StringComparison.OrdinalIgnoreCase) && SceneView.lastActiveSceneView != null)
            {
                cam = SceneView.lastActiveSceneView.camera;
            }
            if (cam == null)
            {
                cam = Camera.main != null ? Camera.main : UnityEngine.Object.FindFirstObjectByType<Camera>();
            }
            if (cam == null)
            {
                throw new NexusRpcException(-32006, "NEXUS_NO_CAMERA_AVAILABLE", $"No active {viewport} or Scene Camera is available to render a screenshot.");
            }

            RenderTexture rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32);
            Texture2D tex = new Texture2D(width, height, TextureFormat.RGB24, mipChain: false);
            RenderTexture prevTarget = cam.targetTexture;
            RenderTexture prevActive = RenderTexture.active;

            try
            {
                cam.targetTexture = rt;
                cam.Render();
                RenderTexture.active = rt;
                tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                tex.Apply();

                byte[] pngBytes = tex.EncodeToPNG();
                string base64Png = Convert.ToBase64String(pngBytes);

                return new Dictionary<string, object>
                {
                    { "projectId", projectId },
                    { "viewport", viewport },
                    { "cameraName", cam.name },
                    { "mimeType", "image/png" },
                    { "width", width },
                    { "height", height },
                    { "byteLength", pngBytes.Length },
                    { "dataBase64", base64Png },
                    { "isTestAdapter", false },
                    { "capturedAt", DateTime.UtcNow.ToString("O") }
                };
            }
            finally
            {
                cam.targetTexture = prevTarget;
                RenderTexture.active = prevActive;
                UnityEngine.Object.DestroyImmediate(rt);
                UnityEngine.Object.DestroyImmediate(tex);
            }
        }

        public static Dictionary<string, object> GetBuildStatus()
        {
            BuildTarget target = EditorUserBuildSettings.activeBuildTarget;
            BuildTargetGroup group = BuildPipeline.GetBuildTargetGroup(target);
            var enabledScenes = new List<object>();

            foreach (EditorBuildSettingsScene scene in EditorBuildSettings.scenes)
            {
                enabledScenes.Add(new Dictionary<string, object>
                {
                    { "path", scene.path },
                    { "enabled", scene.enabled },
                    { "guid", scene.guid.ToString() }
                });
            }

            return new Dictionary<string, object>
            {
                { "isBuildingPlayer", BuildPipeline.isBuildingPlayer },
                { "activeBuildTarget", target.ToString() },
                { "buildTargetGroup", group.ToString() },
                { "developmentBuild", EditorUserBuildSettings.development },
                { "scriptingBackend", PlayerSettings.GetScriptingBackend(group).ToString() },
                { "buildScenes", enabledScenes },
                { "lastBuildReport", NexusUnityStateTracker.GetLastBuildReportSnapshot() }
            };
        }

        private static void GuardSceneMutationAllowed()
        {
            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                throw new NexusRpcException(-32001, "NEXUS_EDITOR_BUSY", "Refusing scene mutation while Unity Editor is compiling scripts or updating assets.");
            }
        }

        private static void GuardScriptMutationAllowed()
        {
            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                throw new NexusRpcException(-32001, "NEXUS_EDITOR_COMPILING", "Refusing script mutation while Unity compilation/import is already in progress.");
            }
            if (EditorApplication.isPlaying)
            {
                throw new NexusRpcException(-32001, "NEXUS_PLAYMODE_ACTIVE", "Refusing script creation or modification while Unity is in Play Mode.");
            }
        }

        private static void MarkSceneDirty(Scene scene)
        {
            if (!EditorApplication.isPlaying && scene.IsValid() && scene.isLoaded)
            {
                EditorSceneManager.MarkSceneDirty(scene);
            }
        }

        private static string NormalizeProjectAssetPath(string rawPath, bool requireCSharp, bool allowFolder = false)
        {
            if (string.IsNullOrWhiteSpace(rawPath))
            {
                throw new NexusRpcException(-32602, "NEXUS_INVALID_ASSET_PATH", "assetPath cannot be empty.");
            }

            string normalized = rawPath.Replace('\\', '/').Trim().TrimEnd('/');
            if (normalized.Contains("..", StringComparison.Ordinal))
            {
                throw new NexusRpcException(-32602, "NEXUS_PATH_TRAVERSAL_BLOCKED", "Path traversal ('..') is forbidden.");
            }
            if (!allowFolder && !normalized.StartsWith("Assets/", StringComparison.Ordinal))
            {
                throw new NexusRpcException(-32602, "NEXUS_SANDBOX_VIOLATION", "Asset operations are strictly restricted to paths inside 'Assets/'.");
            }
            if (allowFolder && !string.Equals(normalized, "Assets", StringComparison.Ordinal) && !normalized.StartsWith("Assets/", StringComparison.Ordinal))
            {
                throw new NexusRpcException(-32602, "NEXUS_SANDBOX_VIOLATION", "Folder operations are strictly restricted to 'Assets' or 'Assets/...'.");
            }
            if (requireCSharp && !normalized.EndsWith(".cs", StringComparison.OrdinalIgnoreCase))
            {
                throw new NexusRpcException(-32602, "NEXUS_INVALID_SCRIPT_EXTENSION", "Unity script operations require a '.cs' file extension.");
            }
            return normalized;
        }

        private static string ToAbsoluteProjectPath(string assetRelativePath)
        {
            string projectRoot = Path.GetFullPath(GetProjectRootPath());
            string combined = Path.GetFullPath(Path.Combine(projectRoot, assetRelativePath));
            string normalizedRoot = projectRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!combined.StartsWith(normalizedRoot, StringComparison.OrdinalIgnoreCase))
            {
                throw new NexusRpcException(-32602, "NEXUS_SANDBOX_VIOLATION", "Resolved path escaped the Unity project directory.");
            }
            return combined;
        }

        private static GameObject ResolveOptionalParent(Dictionary<string, object> args)
        {
            if (args.TryGetValue("parentInstanceId", out object idObj) && idObj != null)
            {
                int parentId = Convert.ToInt32(idObj, CultureInfo.InvariantCulture);
                var obj = EditorUtility.InstanceIDToObject(parentId) as GameObject;
                if (obj == null) throw new NexusRpcException(-32602, "NEXUS_PARENT_NOT_FOUND", $"Parent instanceId {parentId} not found.");
                return obj;
            }
            string parentPath = GetString(args, "parentPath", string.Empty);
            if (!string.IsNullOrEmpty(parentPath))
            {
                GameObject obj = FindGameObjectByHierarchyPath(parentPath);
                if (obj == null) throw new NexusRpcException(-32602, "NEXUS_PARENT_NOT_FOUND", $"Parent object '{parentPath}' not found.");
                return obj;
            }
            return null;
        }

        private static GameObject ResolveGameObjectOrThrow(Dictionary<string, object> args)
        {
            if (args.TryGetValue("instanceId", out object idObj) && idObj != null)
            {
                int id = Convert.ToInt32(idObj, CultureInfo.InvariantCulture);
                if (EditorUtility.InstanceIDToObject(id) is GameObject byId)
                {
                    return byId;
                }
                throw new NexusRpcException(-32602, "NEXUS_OBJECT_NOT_FOUND", $"No GameObject found with instanceId {id}.");
            }

            string hierarchyPath = GetString(args, "path", string.Empty);
            if (!string.IsNullOrEmpty(hierarchyPath))
            {
                GameObject byPath = FindGameObjectByHierarchyPath(hierarchyPath);
                if (byPath != null)
                {
                    return byPath;
                }
                throw new NexusRpcException(-32602, "NEXUS_OBJECT_NOT_FOUND", $"No GameObject found at hierarchy path '{hierarchyPath}'.");
            }

            throw new NexusRpcException(-32602, "NEXUS_MISSING_TARGET", "Provide either 'instanceId' or hierarchy 'path'.");
        }

        private static GameObject FindGameObjectByHierarchyPath(string path)
        {
            string trimmed = path.Trim().TrimStart('/');
            if (string.IsNullOrEmpty(trimmed)) return null;

            for (int s = 0; s < SceneManager.sceneCount; s++)
            {
                Scene scene = SceneManager.GetSceneAt(s);
                if (!scene.isLoaded) continue;
                foreach (GameObject root in scene.GetRootGameObjects())
                {
                    GameObject match = SearchSubtreeByPath(root, root.name, trimmed);
                    if (match != null) return match;
                }
            }
            return GameObject.Find(path);
        }

        private static GameObject SearchSubtreeByPath(GameObject current, string currentPath, string targetPath)
        {
            if (string.Equals(currentPath, targetPath, StringComparison.Ordinal))
            {
                return current;
            }
            if (!targetPath.StartsWith(currentPath + "/", StringComparison.Ordinal))
            {
                return null;
            }
            for (int i = 0; i < current.transform.childCount; i++)
            {
                Transform child = current.transform.GetChild(i);
                GameObject found = SearchSubtreeByPath(child.gameObject, $"{currentPath}/{child.name}", targetPath);
                if (found != null) return found;
            }
            return null;
        }

        private static Type ResolveComponentType(string typeName)
        {
            Type direct = Type.GetType(typeName, throwOnError: false);
            if (direct != null && typeof(Component).IsAssignableFrom(direct)) return direct;

            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type byFullName = asm.GetType(typeName, throwOnError: false);
                if (byFullName != null && typeof(Component).IsAssignableFrom(byFullName)) return byFullName;

                Type inUnityEngine = asm.GetType($"UnityEngine.{typeName}", throwOnError: false);
                if (inUnityEngine != null && typeof(Component).IsAssignableFrom(inUnityEngine)) return inUnityEngine;
            }
            return null;
        }

        private static void ApplyTransformVectors(Transform tr, Dictionary<string, object> args, bool recordUndo)
        {
            if (recordUndo)
            {
                Undo.RecordObject(tr, $"NEXUS Transform {tr.name}");
            }

            bool useLocal = GetBool(args, "local", false);
            if (TryReadVector3(args, "position", out Vector3 pos))
            {
                if (useLocal) tr.localPosition = pos;
                else tr.position = pos;
            }
            if (TryReadVector3(args, "localPosition", out Vector3 lpos))
            {
                tr.localPosition = lpos;
            }
            if (TryReadVector3(args, "eulerAngles", out Vector3 euler))
            {
                if (useLocal) tr.localEulerAngles = euler;
                else tr.eulerAngles = euler;
            }
            if (TryReadVector3(args, "localEulerAngles", out Vector3 leuler))
            {
                tr.localEulerAngles = leuler;
            }
            if (TryReadVector3(args, "localScale", out Vector3 scale))
            {
                tr.localScale = scale;
            }
        }

        private static bool TryReadVector3(Dictionary<string, object> args, string key, out Vector3 vec)
        {
            vec = Vector3.zero;
            if (!args.TryGetValue(key, out object obj) || !(obj is Dictionary<string, object> dict))
            {
                return false;
            }
            float x = dict.TryGetValue("x", out object xo) ? Convert.ToSingle(xo, CultureInfo.InvariantCulture) : 0f;
            float y = dict.TryGetValue("y", out object yo) ? Convert.ToSingle(yo, CultureInfo.InvariantCulture) : 0f;
            float z = dict.TryGetValue("z", out object zo) ? Convert.ToSingle(zo, CultureInfo.InvariantCulture) : 0f;
            vec = new Vector3(x, y, z);
            return true;
        }

        private static void ApplySerializedPropertyValue(SerializedProperty prop, object rawValue)
        {
            switch (prop.propertyType)
            {
                case SerializedPropertyType.Integer:
                    prop.intValue = Convert.ToInt32(rawValue, CultureInfo.InvariantCulture);
                    break;
                case SerializedPropertyType.Boolean:
                    prop.boolValue = Convert.ToBoolean(rawValue, CultureInfo.InvariantCulture);
                    break;
                case SerializedPropertyType.Float:
                    prop.floatValue = Convert.ToSingle(rawValue, CultureInfo.InvariantCulture);
                    break;
                case SerializedPropertyType.String:
                    prop.stringValue = Convert.ToString(rawValue, CultureInfo.InvariantCulture) ?? string.Empty;
                    break;
                case SerializedPropertyType.Enum:
                    prop.enumValueIndex = Convert.ToInt32(rawValue, CultureInfo.InvariantCulture);
                    break;
                case SerializedPropertyType.Vector3:
                    if (rawValue is Dictionary<string, object> v3)
                    {
                        float x = v3.TryGetValue("x", out object xo) ? Convert.ToSingle(xo, CultureInfo.InvariantCulture) : 0f;
                        float y = v3.TryGetValue("y", out object yo) ? Convert.ToSingle(yo, CultureInfo.InvariantCulture) : 0f;
                        float z = v3.TryGetValue("z", out object zo) ? Convert.ToSingle(zo, CultureInfo.InvariantCulture) : 0f;
                        prop.vector3Value = new Vector3(x, y, z);
                    }
                    break;
                default:
                    throw new NexusRpcException(-32602, "NEXUS_UNSUPPORTED_PROPERTY_TYPE", $"SerializedPropertyType '{prop.propertyType}' cannot be written directly.");
            }
        }

        private static Dictionary<string, object> SerializeHierarchyNode(
            GameObject go, string parentPath, int depth, int maxDepth, bool includeInactive)
        {
            string path = string.IsNullOrEmpty(parentPath) ? go.name : $"{parentPath}/{go.name}";
            var compNames = new List<object>();
            foreach (Component comp in go.GetComponents<Component>())
            {
                if (comp != null) compNames.Add(comp.GetType().Name);
            }

            var children = new List<object>();
            if (depth < maxDepth)
            {
                for (int i = 0; i < go.transform.childCount; i++)
                {
                    GameObject childGo = go.transform.GetChild(i).gameObject;
                    if (!includeInactive && !childGo.activeSelf) continue;
                    children.Add(SerializeHierarchyNode(childGo, path, depth + 1, maxDepth, includeInactive));
                }
            }

            return new Dictionary<string, object>
            {
                { "instanceId", go.GetInstanceID() },
                { "name", go.name },
                { "path", path },
                { "activeSelf", go.activeSelf },
                { "activeInHierarchy", go.activeInHierarchy },
                { "tag", go.tag },
                { "layer", LayerMask.LayerToName(go.layer) },
                { "components", compNames },
                { "children", children }
            };
        }

        private static Dictionary<string, object> SerializeGameObjectDetail(GameObject go, bool includeSerializedProperties)
        {
            return new Dictionary<string, object>
            {
                { "instanceId", go.GetInstanceID() },
                { "name", go.name },
                { "path", GetHierarchyPath(go.transform) },
                { "scene", go.scene.path },
                { "activeSelf", go.activeSelf },
                { "activeInHierarchy", go.activeInHierarchy },
                { "tag", go.tag },
                { "layer", LayerMask.LayerToName(go.layer) },
                { "isStatic", go.isStatic },
                { "transform", SerializeTransform(go.transform) },
                { "components", SerializeComponents(go, includeSerializedProperties) }
            };
        }

        private static Dictionary<string, object> SerializeTransform(Transform tr)
        {
            return new Dictionary<string, object>
            {
                { "position", VecToDict(tr.position) },
                { "localPosition", VecToDict(tr.localPosition) },
                { "eulerAngles", VecToDict(tr.eulerAngles) },
                { "localEulerAngles", VecToDict(tr.localEulerAngles) },
                { "localScale", VecToDict(tr.localScale) }
            };
        }

        private static List<object> SerializeComponents(GameObject go, bool includeProperties)
        {
            var list = new List<object>();
            foreach (Component comp in go.GetComponents<Component>())
            {
                if (comp == null) continue;
                var entry = new Dictionary<string, object>
                {
                    { "instanceId", comp.GetInstanceID() },
                    { "type", comp.GetType().FullName },
                    { "name", comp.GetType().Name }
                };

                if (includeProperties)
                {
                    var props = new Dictionary<string, object>();
                    var serialized = new SerializedObject(comp);
                    SerializedProperty it = serialized.GetIterator();
                    int count = 0;
                    if (it.NextVisible(true))
                    {
                        do
                        {
                            if (count >= 24) break;
                            count++;
                            props[it.name] = ReadSerializedPropertyPreview(it);
                        }
                        while (it.NextVisible(false));
                    }
                    entry["properties"] = props;
                }
                list.Add(entry);
            }
            return list;
        }

        private static object ReadSerializedPropertyPreview(SerializedProperty prop)
        {
            switch (prop.propertyType)
            {
                case SerializedPropertyType.Integer: return prop.intValue;
                case SerializedPropertyType.Boolean: return prop.boolValue;
                case SerializedPropertyType.Float: return prop.floatValue;
                case SerializedPropertyType.String: return prop.stringValue;
                case SerializedPropertyType.Vector3: return VecToDict(prop.vector3Value);
                case SerializedPropertyType.Enum: return prop.enumDisplayNames.Length > prop.enumValueIndex && prop.enumValueIndex >= 0 ? prop.enumDisplayNames[prop.enumValueIndex] : prop.enumValueIndex;
                default: return prop.propertyType.ToString();
            }
        }

        private static Dictionary<string, object> VecToDict(Vector3 v)
        {
            return new Dictionary<string, object>
            {
                { "x", v.x },
                { "y", v.y },
                { "z", v.z }
            };
        }

        private static string GetHierarchyPath(Transform tr)
        {
            var stack = new Stack<string>();
            Transform curr = tr;
            while (curr != null)
            {
                stack.Push(curr.name);
                curr = curr.parent;
            }
            return string.Join("/", stack);
        }

        private static string GetString(Dictionary<string, object> args, string key, string fallback)
        {
            if (args != null && args.TryGetValue(key, out object val) && val != null)
            {
                return Convert.ToString(val, CultureInfo.InvariantCulture) ?? fallback;
            }
            return fallback;
        }

        private static int GetInt(Dictionary<string, object> args, string key, int fallback)
        {
            if (args != null && args.TryGetValue(key, out object val) && val != null)
            {
                return Convert.ToInt32(val, CultureInfo.InvariantCulture);
            }
            return fallback;
        }

        private static bool GetBool(Dictionary<string, object> args, string key, bool fallback)
        {
            if (args != null && args.TryGetValue(key, out object val) && val != null)
            {
                return Convert.ToBoolean(val, CultureInfo.InvariantCulture);
            }
            return fallback;
        }
    }
}
#endif
