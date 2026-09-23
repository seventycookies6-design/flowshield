using System.Windows;
using System.Windows.Shell;
using FlowShield.Models;

namespace FlowShield.Services;

/// <summary>
/// The taskbar Jump List (1.0.10, spec 5): "Start sprint" and one "Start
/// &lt;template&gt;" per template. Each runs FlowShield with --start-sprint,
/// which the single-instance pipe hands to a copy already running. A per-user
/// shell feature: no registry, no admin.
/// </summary>
public static class JumpListService
{
    public static void Rebuild(IReadOnlyList<StudyTemplate> templates, string exePath)
    {
        try
        {
            var list = new JumpList { ShowRecentCategory = false, ShowFrequentCategory = false };
            list.JumpItems.Add(new JumpTask
            {
                Title = "Start sprint",
                Description = "Start a sprint with your last settings",
                ApplicationPath = exePath,
                Arguments = StartSprintArg.Flag,
                IconResourcePath = exePath,
            });
            foreach (var t in templates)
            {
                if (StartSprintArg.For(t.Id) is not { } arguments)
                {
                    Log.Warn($"jump list: no entry for template \"{t.Name}\"; its id can't go on a command line");
                    continue;
                }
                list.JumpItems.Add(new JumpTask
                {
                    Title = JumpListText.Title(t.Name),   // menu text: & would be a mnemonic
                    Description = $"{t.SprintMinutes} minutes at {t.Shield}",
                    ApplicationPath = exePath,
                    Arguments = arguments,
                    IconResourcePath = exePath,
                });
            }

            // An entry the shell refuses (a path it can't resolve, a bad icon)
            // is dropped, not thrown; without this it would vanish without a trace.
            var wanted = list.JumpItems.Count;
            list.JumpItemsRejected += (_, e) =>
            {
                var why = string.Join(", ", e.RejectedItems.Select((item, i) =>
                    $"\"{(item as JumpTask)?.Title ?? item.GetType().Name}\" ({e.RejectionReasons[i]})"));
                Log.Warn($"jump list: the shell rejected {e.RejectedItems.Count} of {wanted} entries: {why}");
            };
            // SetJumpList applies the list itself; JumpItems then holds what the shell kept.
            JumpList.SetJumpList(Application.Current, list);
            Log.Info($"jump list: {list.JumpItems.Count} entries");
        }
        catch (Exception ex)
        {
            // A missing Jump List costs a shortcut, never the app.
            Log.Warn($"could not build the jump list: {ex.Message}");
        }
    }

    /// <summary>
    /// Settings, Your data, Delete everything (#311). The list holds template
    /// names and lengths in a file Windows keeps in the user profile, outside
    /// settings.json, so it goes with the rest. An empty list, applied: no
    /// entries at all until the next start builds one from what is there then.
    /// Needs the Application, so it runs on the UI thread.
    /// </summary>
    public static void Clear()
    {
        try
        {
            JumpList.SetJumpList(Application.Current,
                new JumpList { ShowRecentCategory = false, ShowFrequentCategory = false });
            Log.Info("jump list: cleared");
        }
        catch (Exception ex)
        {
            // As with Rebuild: a list left behind costs a shortcut, never the delete.
            Log.Warn($"could not clear the jump list: {ex.Message}");
        }
    }
}
