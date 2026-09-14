using System.IO;
using System.IO.Pipes;
using System.Text;

namespace FlowShield.Services;

/// <summary>
/// Keeps FlowShield to one running copy per Windows user (roadmap 1.3).
///
/// Two copies meant two blockers and two writers to one settings file, each
/// able to overwrite the other's sprint records. The first copy holds a named
/// mutex and listens on a named pipe; a later launch sends its arguments down
/// the pipe (so the running copy comes forward, and later handles
/// flowshield:// links) and exits before loading settings or blocking anything.
/// </summary>
public sealed class SingleInstance : IDisposable
{
    private static readonly string UserKey = Sanitize(Environment.UserDomainName + "_" + Environment.UserName);

    /// <summary>Local\ scopes the mutex to this sign-in session; the user in the name keeps accounts apart.</summary>
    public static readonly string MutexName = @"Local\FlowShield.SingleInstance." + UserKey;
    public static readonly string PipeName = "FlowShield.SingleInstance." + UserKey;

    private readonly Mutex _mutex;
    private readonly CancellationTokenSource _stop = new();

    private SingleInstance(Mutex mutex) => _mutex = mutex;

    /// <summary>
    /// Takes the per-user lock. Returns null if another copy holds it; a copy
    /// that crashed or was ended from Task Manager leaves the mutex abandoned,
    /// which counts as free.
    /// </summary>
    public static SingleInstance? TryAcquire()
    {
        var mutex = new Mutex(false, MutexName);
        bool owned;
        try { owned = mutex.WaitOne(0); }
        catch (AbandonedMutexException) { owned = true; }

        if (owned) return new SingleInstance(mutex);
        mutex.Dispose();
        return null;
    }

    /// <summary>Hands this launch's arguments to the running copy. False if it didn't answer.</summary>
    public static bool SendToRunningInstance(string[] args, int timeoutMs = 3000)
    {
        try
        {
            using var client = new NamedPipeClientStream(".", PipeName, PipeDirection.Out);
            client.Connect(timeoutMs);
            var payload = Encoding.UTF8.GetBytes(string.Join('\n', args));
            client.Write(payload, 0, payload.Length);
            client.Flush();
            return true;
        }
        catch (Exception ex)
        {
            Log.Info($"single instance: couldn't reach the running copy ({ex.Message})");
            return false;
        }
    }

    /// <summary>Listens for later launches; <paramref name="onActivated"/> runs on a background thread.</summary>
    public void Listen(Action<string[]> onActivated)
    {
        _ = Task.Run(async () =>
        {
            while (!_stop.IsCancellationRequested)
            {
                try
                {
                    await using var server = new NamedPipeServerStream(
                        PipeName, PipeDirection.In, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous);
                    await server.WaitForConnectionAsync(_stop.Token);
                    using var reader = new StreamReader(server, Encoding.UTF8);
                    var text = await reader.ReadToEndAsync(_stop.Token);
                    var args = text.Split('\n', StringSplitOptions.RemoveEmptyEntries);
                    onActivated(args);
                }
                catch (OperationCanceledException) { break; }
                catch (Exception ex)
                {
                    Log.Error("single instance listener", ex);
                    await Task.Delay(500);
                }
            }
        });
    }

    private static string Sanitize(string s) =>
        new(s.Select(c => char.IsLetterOrDigit(c) ? c : '_').ToArray());

    public void Dispose()
    {
        _stop.Cancel();
        try { _mutex.ReleaseMutex(); } catch { /* not owned on this thread */ }
        _mutex.Dispose();
    }
}
