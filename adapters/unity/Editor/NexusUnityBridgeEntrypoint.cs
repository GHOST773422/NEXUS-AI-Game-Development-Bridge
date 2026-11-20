#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEditor;
using UnityEngine;

namespace Nexus.Bridge.Editor
{
    /// <summary>
    /// Primary NEXUS Unity Editor adapter entrypoint initialized cleanly on domain load.
    /// Manages loopback port assignment (for multi-project Unity instances), main-thread dispatch,
    /// compilation/log/build tracking, and domain reload safety.
    /// </summary>
    [InitializeOnLoad]
    public static class NexusUnityBridgeEntrypoint
    {
        public const int DefaultPort = 47201;

        private static NexusUnityTcpServer _server;
        private static int _activePort = DefaultPort;

        public static int ActivePort => _activePort;
        public static bool IsListening => _server != null && _server.IsListening;
        public static int ActiveClientCount => _server != null ? _server.ActiveClientCount : 0;

        static NexusUnityBridgeEntrypoint()
        {
            NexusMainThreadDispatcher.InitializeOnMainThread();
            NexusUnityStateTracker.Initialize();

            AssemblyReloadEvents.beforeAssemblyReload += OnBeforeAssemblyReload;
            AssemblyReloadEvents.afterAssemblyReload += OnAfterAssemblyReload;
            EditorApplication.quitting += OnEditorQuitting;

            StartListener(ResolveConfiguredPort());
        }

        public static int ResolveConfiguredPort()
        {
            string envPort = Environment.GetEnvironmentVariable("NEXUS_UNITY_PORT");
            if (!string.IsNullOrEmpty(envPort) &&
                int.TryParse(envPort, NumberStyles.Integer, CultureInfo.InvariantCulture, out int parsedEnv) &&
                parsedEnv >= 1024 && parsedEnv <= 65535)
            {
                return parsedEnv;
            }

            string projectKey = $"NEXUS_UNITY_PORT_{NexusUnityHandlers.ComputeProjectId(NexusUnityHandlers.GetProjectRootPath())}";
            int prefPort = EditorPrefs.GetInt(projectKey, DefaultPort);
            if (prefPort >= 1024 && prefPort <= 65535)
            {
                return prefPort;
            }
            return DefaultPort;
        }

        public static void SetProjectPort(int port)
        {
            if (port < 1024 || port > 65535)
            {
                throw new ArgumentOutOfRangeException(nameof(port), "Port must be between 1024 and 65535.");
            }
            string projectKey = $"NEXUS_UNITY_PORT_{NexusUnityHandlers.ComputeProjectId(NexusUnityHandlers.GetProjectRootPath())}";
            EditorPrefs.SetInt(projectKey, port);
            RestartListener(port);
        }

        public static void StartListener(int port)
        {
            if (_server != null && _server.IsListening && _server.Port == port)
            {
                return;
            }
            StopListener();
            _activePort = port;
            _server = new NexusUnityTcpServer(port);
            _server.Start();
        }

        public static void StopListener()
        {
            if (_server != null)
            {
                _server.Stop();
                _server = null;
            }
        }

        public static void RestartListener(int port)
        {
            StopListener();
            StartListener(port);
        }

        public static NexusEngineHealth CheckHealth()
        {
            return new NexusEngineHealth
            {
                engine = "Unity",
                unityVersion = Application.unityVersion,
                isCompiling = EditorApplication.isCompiling,
                isUpdating = EditorApplication.isUpdating,
                isPlaying = EditorApplication.isPlaying,
                mainThreadResponsive = true,
                listenerPort = _activePort,
                timestamp = DateTime.UtcNow.ToString("O")
            };
        }

        public static IReadOnlyList<NexusToolDescriptor> DiscoverTools()
        {
            return NexusUnityToolRegistry.BuildToolCatalog();
        }

        private static void OnBeforeAssemblyReload()
        {
            StopListener();
            NexusUnityStateTracker.Shutdown();
        }

        private static void OnAfterAssemblyReload()
        {
            NexusMainThreadDispatcher.InitializeOnMainThread();
            NexusUnityStateTracker.Initialize();
            StartListener(ResolveConfiguredPort());
        }

        private static void OnEditorQuitting()
        {
            StopListener();
            NexusUnityStateTracker.Shutdown();
            NexusMainThreadDispatcher.Shutdown();
        }
    }

    public sealed class NexusBridgeStatusWindow : EditorWindow
    {
        private int _portDraft = NexusUnityBridgeEntrypoint.DefaultPort;

        [MenuItem("NEXUS/Unity Bridge Status")]
        public static void ShowWindow()
        {
            var win = GetWindow<NexusBridgeStatusWindow>("NEXUS Unity Bridge");
            win.minSize = new Vector2(420f, 300f);
            win._portDraft = NexusUnityBridgeEntrypoint.ActivePort;
        }

        private void OnEnable()
        {
            _portDraft = NexusUnityBridgeEntrypoint.ActivePort;
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("NEXUS Unity Editor Adapter", EditorStyles.boldLabel);
            EditorGUILayout.Space(6);

            string root = NexusUnityHandlers.GetProjectRootPath();
            string projectId = NexusUnityHandlers.ComputeProjectId(root);

            EditorGUILayout.LabelField("Project Name", Application.productName);
            EditorGUILayout.LabelField("Project ID", projectId);
            EditorGUILayout.LabelField("Unity Version", Application.unityVersion);
            EditorGUILayout.LabelField("Bind Host", "127.0.0.1 (Loopback Only)");
            EditorGUILayout.LabelField("Listener Status", NexusUnityBridgeEntrypoint.IsListening ? "Listening" : "Stopped");
            EditorGUILayout.LabelField("Connected Clients", NexusUnityBridgeEntrypoint.ActiveClientCount.ToString(CultureInfo.InvariantCulture));
            EditorGUILayout.LabelField("Compiling / Updating", $"{EditorApplication.isCompiling} / {EditorApplication.isUpdating}");
            EditorGUILayout.LabelField("Registered Tools", NexusUnityToolRegistry.BuildToolCatalog().Count.ToString(CultureInfo.InvariantCulture));

            EditorGUILayout.Space(10);
            EditorGUILayout.LabelField("Multi-Project Loopback Port", EditorStyles.boldLabel);
            _portDraft = EditorGUILayout.IntField("TCP Port (1024-65535)", _portDraft);

            EditorGUILayout.BeginHorizontal();
            if (GUILayout.Button("Apply Port & Restart Listener"))
            {
                NexusUnityBridgeEntrypoint.SetProjectPort(_portDraft);
            }
            if (GUILayout.Button("Stop Listener"))
            {
                NexusUnityBridgeEntrypoint.StopListener();
            }
            EditorGUILayout.EndHorizontal();
        }
    }
}
#endif
