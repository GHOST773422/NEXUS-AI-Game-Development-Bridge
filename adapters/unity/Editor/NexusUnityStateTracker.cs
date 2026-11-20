#if UNITY_EDITOR
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.Compilation;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Nexus.Bridge.Editor
{
    /// <summary>
    /// Captures Unity Editor logs, C# compilation diagnostics, Play Mode transitions, and BuildReports.
    /// Safe across threaded log callbacks and main-thread Unity Editor callbacks.
    /// </summary>
    public sealed class NexusUnityStateTracker : IPreprocessBuildWithReport, IPostprocessBuildWithReport
    {
        private const int MaxLogEntries = 500;
        private const int MaxCompilerMessages = 200;

        private static readonly object StateLock = new object();
        private static readonly ConcurrentQueue<Dictionary<string, object>> LogBuffer =
            new ConcurrentQueue<Dictionary<string, object>>();

        private static readonly List<Dictionary<string, object>> LastCompilerMessages =
            new List<Dictionary<string, object>>();

        private static bool _initialized;
        private static string _lastCompilationId = string.Empty;
        private static string _lastCompilationStartedAt = string.Empty;
        private static string _lastCompilationFinishedAt = string.Empty;
        private static int _lastErrorCount;
        private static int _lastWarningCount;
        private static readonly List<string> CompiledAssemblies = new List<string>();

        private static Dictionary<string, object> _lastBuildReport = new Dictionary<string, object>
        {
            { "hasBuildReport", false },
            { "result", "None" }
        };

        public static event Action<string, Dictionary<string, object>> OnEditorNotification;

        public int callbackOrder => 0;

        internal static void Initialize()
        {
            if (_initialized) return;
            _initialized = true;

            Application.logMessageReceivedThreaded += HandleLogMessage;
            CompilationPipeline.compilationStarted += HandleCompilationStarted;
            CompilationPipeline.compilationFinished += HandleCompilationFinished;
            CompilationPipeline.assemblyCompilationFinished += HandleAssemblyCompilationFinished;
            EditorApplication.playModeStateChanged += HandlePlayModeChanged;
            EditorSceneManager.sceneSaved += HandleSceneSaved;
        }

        internal static void Shutdown()
        {
            if (!_initialized) return;
            _initialized = false;

            Application.logMessageReceivedThreaded -= HandleLogMessage;
            CompilationPipeline.compilationStarted -= HandleCompilationStarted;
            CompilationPipeline.compilationFinished -= HandleCompilationFinished;
            CompilationPipeline.assemblyCompilationFinished -= HandleAssemblyCompilationFinished;
            EditorApplication.playModeStateChanged -= HandlePlayModeChanged;
            EditorSceneManager.sceneSaved -= HandleSceneSaved;
        }

        private static void HandleLogMessage(string condition, string stackTrace, LogType type)
        {
            string severity = type.ToString();
            string ts = DateTime.UtcNow.ToString("O");
            string clippedStack = string.IsNullOrEmpty(stackTrace)
                ? string.Empty
                : (stackTrace.Length > 1000 ? stackTrace.Substring(0, 1000) : stackTrace);

            var entry = new Dictionary<string, object>
            {
                { "timestamp", ts },
                { "severity", severity },
                { "message", condition ?? string.Empty },
                { "stackTrace", clippedStack }
            };

            LogBuffer.Enqueue(entry);
            while (LogBuffer.Count > MaxLogEntries)
            {
                LogBuffer.TryDequeue(out _);
            }

            OnEditorNotification?.Invoke(
                "adapter.log",
                new Dictionary<string, object>
                {
                    { "severity", severity },
                    { "message", condition ?? string.Empty },
                    { "timestamp", ts }
                }
            );
        }

        private static void HandleCompilationStarted(object context)
        {
            lock (StateLock)
            {
                _lastCompilationId = Guid.NewGuid().ToString("N");
                _lastCompilationStartedAt = DateTime.UtcNow.ToString("O");
                _lastErrorCount = 0;
                _lastWarningCount = 0;
                LastCompilerMessages.Clear();
                CompiledAssemblies.Clear();
            }

            OnEditorNotification?.Invoke(
                "adapter.event",
                new Dictionary<string, object>
                {
                    { "event", "compilation.started" },
                    { "timestamp", DateTime.UtcNow.ToString("O") }
                }
            );
        }

        private static void HandleAssemblyCompilationFinished(string assemblyPath, CompilerMessage[] messages)
        {
            lock (StateLock)
            {
                if (!string.IsNullOrEmpty(assemblyPath))
                {
                    CompiledAssemblies.Add(assemblyPath);
                }

                if (messages == null) return;
                foreach (CompilerMessage msg in messages)
                {
                    if (msg.type == CompilerMessageType.Error) _lastErrorCount++;
                    else if (msg.type == CompilerMessageType.Warning) _lastWarningCount++;

                    if (LastCompilerMessages.Count < MaxCompilerMessages)
                    {
                        LastCompilerMessages.Add(new Dictionary<string, object>
                        {
                            { "assembly", assemblyPath ?? string.Empty },
                            { "type", msg.type.ToString() },
                            { "message", msg.message ?? string.Empty },
                            { "file", msg.file ?? string.Empty },
                            { "line", msg.line },
                            { "column", msg.column }
                        });
                    }
                }
            }
        }

        private static void HandleCompilationFinished(object context)
        {
            int errors;
            int warnings;
            string finishedAt = DateTime.UtcNow.ToString("O");
            lock (StateLock)
            {
                _lastCompilationFinishedAt = finishedAt;
                errors = _lastErrorCount;
                warnings = _lastWarningCount;
            }

            OnEditorNotification?.Invoke(
                "adapter.event",
                new Dictionary<string, object>
                {
                    { "event", "compilation.finished" },
                    { "errorCount", errors },
                    { "warningCount", warnings },
                    { "timestamp", finishedAt }
                }
            );
        }

        private static void HandlePlayModeChanged(PlayModeStateChange change)
        {
            OnEditorNotification?.Invoke(
                "adapter.event",
                new Dictionary<string, object>
                {
                    { "event", "playmode.changed" },
                    { "state", change.ToString() },
                    { "isPlaying", EditorApplication.isPlaying },
                    { "isPaused", EditorApplication.isPaused },
                    { "timestamp", DateTime.UtcNow.ToString("O") }
                }
            );
        }

        private static void HandleSceneSaved(Scene scene)
        {
            OnEditorNotification?.Invoke(
                "adapter.event",
                new Dictionary<string, object>
                {
                    { "event", "scene.saved" },
                    { "sceneName", scene.name },
                    { "scenePath", scene.path },
                    { "timestamp", DateTime.UtcNow.ToString("O") }
                }
            );
        }

        public void OnPreprocessBuild(BuildReport report)
        {
            lock (StateLock)
            {
                _lastBuildReport = new Dictionary<string, object>
                {
                    { "hasBuildReport", true },
                    { "result", "InProgress" },
                    { "platform", report.summary.platform.ToString() },
                    { "outputPath", report.summary.outputPath ?? string.Empty },
                    { "startedAt", DateTime.UtcNow.ToString("O") }
                };
            }
        }

        public void OnPostprocessBuild(BuildReport report)
        {
            lock (StateLock)
            {
                _lastBuildReport = new Dictionary<string, object>
                {
                    { "hasBuildReport", true },
                    { "result", report.summary.result.ToString() },
                    { "platform", report.summary.platform.ToString() },
                    { "outputPath", report.summary.outputPath ?? string.Empty },
                    { "totalErrors", report.summary.totalErrors },
                    { "totalWarnings", report.summary.totalWarnings },
                    { "totalSizeBytes", (long)report.summary.totalSize },
                    { "totalTimeSeconds", report.summary.totalTime.TotalSeconds },
                    { "finishedAt", DateTime.UtcNow.ToString("O") }
                };
            }
        }

        public static List<object> GetConsoleLogs(string severityFilter, int limit, bool clearAfterRead)
        {
            var snapshot = LogBuffer.ToArray();
            if (clearAfterRead)
            {
                while (LogBuffer.TryDequeue(out _))
                {
                }
            }

            var filtered = new List<object>();
            string normalizedFilter = string.IsNullOrEmpty(severityFilter)
                ? string.Empty
                : severityFilter.Trim().ToLowerInvariant();

            for (int i = snapshot.Length - 1; i >= 0; i--)
            {
                Dictionary<string, object> item = snapshot[i];
                if (!string.IsNullOrEmpty(normalizedFilter))
                {
                    string itemSeverity = Convert.ToString(item["severity"])?.ToLowerInvariant() ?? string.Empty;
                    if (!string.Equals(itemSeverity, normalizedFilter, StringComparison.Ordinal))
                    {
                        continue;
                    }
                }
                filtered.Add(item);
                if (limit > 0 && filtered.Count >= limit)
                {
                    break;
                }
            }

            filtered.Reverse();
            return filtered;
        }

        public static Dictionary<string, object> GetCompilationSummary()
        {
            lock (StateLock)
            {
                return new Dictionary<string, object>
                {
                    { "isCompiling", EditorApplication.isCompiling },
                    { "isUpdating", EditorApplication.isUpdating },
                    { "compilationId", _lastCompilationId },
                    { "lastStartedAt", _lastCompilationStartedAt },
                    { "lastFinishedAt", _lastCompilationFinishedAt },
                    { "errorCount", _lastErrorCount },
                    { "warningCount", _lastWarningCount },
                    { "compiledAssemblies", new List<object>(CompiledAssemblies) },
                    { "messages", new List<object>(LastCompilerMessages) }
                };
            }
        }

        public static Dictionary<string, object> GetLastBuildReportSnapshot()
        {
            lock (StateLock)
            {
                return new Dictionary<string, object>(_lastBuildReport);
            }
        }
    }
}
#endif
