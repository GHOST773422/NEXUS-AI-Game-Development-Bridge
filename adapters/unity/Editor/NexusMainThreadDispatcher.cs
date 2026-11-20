#if UNITY_EDITOR
using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;

namespace Nexus.Bridge.Editor
{
    /// <summary>
    /// Marshals Unity Editor API operations safely from TCP listener background threads onto Unity's main editor thread.
    /// </summary>
    public static class NexusMainThreadDispatcher
    {
        private static readonly ConcurrentQueue<Action> PendingQueue = new ConcurrentQueue<Action>();
        private static int _mainThreadId = -1;
        private static bool _hooked;

        public static int MainThreadId => _mainThreadId;
        public static bool IsMainThread => Thread.CurrentThread.ManagedThreadId == _mainThreadId;

        internal static void InitializeOnMainThread()
        {
            _mainThreadId = Thread.CurrentThread.ManagedThreadId;
            if (!_hooked)
            {
                EditorApplication.update += DrainPendingActions;
                _hooked = true;
            }
        }

        internal static void Shutdown()
        {
            if (_hooked)
            {
                EditorApplication.update -= DrainPendingActions;
                _hooked = false;
            }
            while (PendingQueue.TryDequeue(out _))
            {
            }
        }

        private static void DrainPendingActions()
        {
            int processed = 0;
            while (processed < 64 && PendingQueue.TryDequeue(out Action action))
            {
                processed++;
                try
                {
                    action?.Invoke();
                }
                catch
                {
                    // Individual TaskCompletionSources capture action exceptions cleanly.
                }
            }
        }

        public static Task<T> InvokeAsync<T>(Func<T> func, int timeoutMs = 15000)
        {
            if (func == null) throw new ArgumentNullException(nameof(func));

            if (IsMainThread)
            {
                try
                {
                    return Task.FromResult(func());
                }
                catch (Exception ex)
                {
                    return Task.FromException<T>(ex);
                }
            }

            var tcs = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
            PendingQueue.Enqueue(() =>
            {
                try
                {
                    tcs.TrySetResult(func());
                }
                catch (Exception ex)
                {
                    tcs.TrySetException(ex);
                }
            });

            if (timeoutMs <= 0)
            {
                return tcs.Task;
            }

            return WaitWithTimeoutAsync(tcs.Task, timeoutMs);
        }

        private static async Task<T> WaitWithTimeoutAsync<T>(Task<T> task, int timeoutMs)
        {
            Task completed = await Task.WhenAny(task, Task.Delay(timeoutMs)).ConfigureAwait(false);
            if (completed != task)
            {
                throw new NexusRpcException(
                    -32002,
                    "NEXUS_UNITY_MAIN_THREAD_TIMEOUT",
                    $"Unity main editor thread did not respond within {timeoutMs}ms."
                );
            }
            return await task.ConfigureAwait(false);
        }
    }
}
#endif
