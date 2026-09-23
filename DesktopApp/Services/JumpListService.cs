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
                    Title = $"Start {t.Name}",
                    Description = $"{t.SprintMinutes} minutes at {t.Shield}",
                    ApplicationPath = exePath,
                    Arguments = arguments,
                    IconResourcePath = exePath,
                });
            }
            JumpList.SetJumpList(Application.Current, list);
            list.Apply();
        }
        catch (Exception ex)
        {
            // A missing Jump List costs a shortcut, never the app.
            Log.Warn($"could not build the jump list: {ex.Message}");
        }
    }
}
