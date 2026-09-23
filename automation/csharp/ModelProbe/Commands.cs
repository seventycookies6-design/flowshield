using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using FlowShield.Models;

namespace FlowShield.ModelProbe;

internal static class Commands
{
    /// <summary>Probe times are seconds after this instant, so tests stay readable.</summary>
    private static readonly DateTime Epoch = new(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc);

    public static JsonNode Run(JsonObject request)
    {
        var cmd = (string?)request["cmd"] ?? "";
        return cmd switch
        {
            "ping" => new JsonObject { ["ok"] = true },
            "soft-sequence" => SoftSequence(request),
            "soft-wait" => SoftWait(request),
            "soft-copy" => SoftCopy(request),
            "template-builtins" => new JsonObject
            {
                ["templates"] = JsonSerializer.SerializeToNode(StudyTemplate.BuiltIns()),
            },
            "template-normalize" => TemplateNormalize(request),
            "schedule-start-on" => ScheduleStartOn(request),
            "schedule-next" => ScheduleNext(request),
            "schedule-between" => ScheduleBetween(request),
            "schedule-skip" => ScheduleSkip(request),
            "schedule-normalize" => ScheduleNormalize(request),
            "text-days" => new JsonObject
            {
                ["text"] = ScheduleText.Days(request["days"]!.AsArray().Select(d => (DayOfWeek)(int)d!)),
            },
            "text-next-up" => new JsonObject
            {
                ["text"] = ScheduleText.NextUp((string)request["name"]!,
                    DateTime.Parse((string)request["start"]!, CultureInfo.InvariantCulture),
                    DateTime.Parse((string)request["now"]!, CultureInfo.InvariantCulture)),
            },
            "settings-ensure-templates" => SettingsEnsureTemplates(request),
            "settings-delete-template" => SettingsDeleteTemplate(request),
            "settings-restore-builtins" => SettingsRestore(request),
            "settings-profile-for" => SettingsProfileFor(request),
            "settings-unique-template-name" => SettingsUniqueTemplateName(request),
            _ => throw new ArgumentException($"unknown command '{cmd}'"),
        };
    }

    /// <summary>
    /// Runs SoftOverlayPolicy through a list of steps:
    /// {"op": "show"|"left"|"allow"|"back"|"close"|"reset"|"tries"|"turned",
    ///  "app": "Discord", "at": seconds}.
    /// Each step's result is the method's return value, or null for void methods;
    /// "tries" and "turned" read the two counters.
    /// </summary>
    private static JsonNode SoftSequence(JsonObject request)
    {
        var policy = new SoftOverlayPolicy();
        var results = new JsonArray();
        foreach (var step in request["steps"]!.AsArray())
        {
            var op = (string)step!["op"]!;
            var app = (string?)step["app"] ?? "";
            var at = Epoch.AddSeconds((double?)step["at"] ?? 0);
            JsonNode? result = op switch
            {
                "show" => (JsonNode)policy.ShouldShow(app, at),
                "left" => (JsonNode)policy.LeftTheForeground(),
                "allow" => Do(() => policy.AllowFiveMinutes(app, at)),
                "back" => Do(() => policy.BackToWork(app, at)),
                "close" => Do(() => policy.CloseIt(app, at)),
                "reset" => Do(policy.Reset),
                "tries" => (JsonNode)policy.Tries,
                "turned" => (JsonNode)policy.TurnedBack,
                _ => throw new ArgumentException($"unknown soft op '{op}'"),
            };
            results.Add(result);
        }
        return new JsonObject { ["results"] = results };
    }

    /// <summary>{"try": n, "short": bool}: the wait before Allow on try n, in seconds.</summary>
    private static JsonNode SoftWait(JsonObject request)
    {
        // The flag is static: reset it even when the request is malformed, so
        // it cannot leak into a later command in the same process.
        SoftOverlayPolicy.UseShortTimers = (bool?)request["short"] ?? false;
        try
        {
            var seconds = SoftOverlayPolicy.AllowWait((int)request["try"]!).TotalSeconds;
            return new JsonObject { ["seconds"] = seconds };
        }
        finally
        {
            SoftOverlayPolicy.UseShortTimers = false;
        }
    }

    /// <summary>
    /// {"try": n, "app", "ends": local ISO time, "intention", "allow_left": seconds}:
    /// every piece of the notice's wording for that try.
    /// </summary>
    private static JsonNode SoftCopy(JsonObject request)
    {
        var n = (int)request["try"]!;
        var app = (string?)request["app"] ?? "Discord";
        var ends = DateTime.Parse((string?)request["ends"] ?? "2026-09-28T17:45:00", CultureInfo.InvariantCulture);
        return new JsonObject
        {
            ["sentence"] = SoftOverlayCopy.Sentence(app, ends, n),
            ["try_line"] = SoftOverlayCopy.TryLine(n),
            ["intention"] = SoftOverlayCopy.Intention((string?)request["intention"]),
            ["allow_label"] = SoftOverlayCopy.AllowLabel(TimeSpan.FromSeconds((double?)request["allow_left"] ?? 0)),
            ["close_note"] = SoftOverlayCopy.CloseNote,
        };
    }

    /// <summary>
    /// Runs StudyTemplate.Normalize on {"template": {...}} and returns the
    /// template as it came out, with whether anything changed. IsBuiltIn is
    /// read first, as a caller that runs before Normalize would.
    /// </summary>
    private static JsonNode TemplateNormalize(JsonObject request)
    {
        var template = request["template"].Deserialize<StudyTemplate>()!;
        var isBuiltInBefore = template.IsBuiltIn;
        var changed = template.Normalize();
        return new JsonObject
        {
            ["is_built_in_before"] = isBuiltInBefore,
            ["template"] = JsonSerializer.SerializeToNode(template),
            ["changed"] = changed,
        };
    }

    private static SprintSchedule ScheduleOf(JsonObject request) =>
        request["schedule"].Deserialize<SprintSchedule>()!;

    /// <summary>A Windows time-zone id, e.g. "Eastern Standard Time", so the test doesn't depend on this PC's zone.</summary>
    private static TimeZoneInfo ZoneOf(JsonObject request) =>
        TimeZoneInfo.FindSystemTimeZoneById((string)request["zone"]!);

    /// <summary>"2026-09-28T21:00:00Z" as a DateTime with Kind = Utc.</summary>
    private static DateTime Utc(string text) =>
        DateTime.Parse(text, CultureInfo.InvariantCulture,
            DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal);

    private static JsonNode? Iso(DateTime? utc) =>
        utc is { } t ? JsonValue.Create(t.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture)) : null;

    /// <summary>{"schedule", "date": "yyyy-MM-dd" (local), "zone"} -> {"utc": the start that day, or null}.</summary>
    private static JsonNode ScheduleStartOn(JsonObject request) => new JsonObject
    {
        ["utc"] = Iso(ScheduleMatcher.StartOnDateUtc(ScheduleOf(request),
            DateTime.Parse((string)request["date"]!, CultureInfo.InvariantCulture), ZoneOf(request))),
    };

    /// <summary>{"schedule", "after": UTC, "zone"} -> {"utc": the first start strictly after, or null}.</summary>
    private static JsonNode ScheduleNext(JsonObject request) => new JsonObject
    {
        ["utc"] = Iso(ScheduleMatcher.NextStartUtc(ScheduleOf(request),
            Utc((string)request["after"]!), ZoneOf(request))),
    };

    /// <summary>{"schedule", "from": UTC, "to": UTC, "zone"} -> {"utc": [every start in (from, to]]}.</summary>
    private static JsonNode ScheduleBetween(JsonObject request)
    {
        var starts = ScheduleMatcher.StartsBetweenUtc(ScheduleOf(request),
            Utc((string)request["from"]!), Utc((string)request["to"]!), ZoneOf(request));
        return new JsonObject { ["utc"] = new JsonArray(starts.Select(s => Iso(s)).ToArray()) };
    }

    /// <summary>
    /// Skips each local date in "skip" in turn, then answers IsSkipped for each
    /// date in "query", with the remembered dates as they came out. With
    /// "roundtrip": true the schedule goes through JSON between the two, as it
    /// would through the settings file; "stored" is what the file would hold.
    /// </summary>
    private static JsonNode ScheduleSkip(JsonObject request)
    {
        var schedule = ScheduleOf(request);
        foreach (var d in request["skip"]!.AsArray())
            schedule.Skip(DateTime.Parse((string)d!, CultureInfo.InvariantCulture));

        var stored = JsonSerializer.SerializeToNode(schedule)!["SkippedDatesLocal"]!.AsArray()
            .Select(d => (JsonNode)(string)d!).ToArray();
        if ((bool?)request["roundtrip"] == true)
            schedule = JsonSerializer.Deserialize<SprintSchedule>(JsonSerializer.Serialize(schedule))!;

        var queries = request["query"]!.AsArray()
            .Select(d => (JsonNode)schedule.IsSkipped(DateTime.Parse((string)d!, CultureInfo.InvariantCulture)))
            .ToArray();
        return new JsonObject
        {
            ["skipped"] = new JsonArray(schedule.SkippedDatesLocal
                .Select(d => (JsonNode)d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)).ToArray()),
            ["stored"] = new JsonArray(stored),
            ["is_skipped"] = new JsonArray(queries),
        };
    }

    /// <summary>Runs SprintSchedule.Normalize, like TemplateNormalize.</summary>
    private static JsonNode ScheduleNormalize(JsonObject request)
    {
        var schedule = ScheduleOf(request);
        var changed = schedule.Normalize();
        return new JsonObject
        {
            ["schedule"] = JsonSerializer.SerializeToNode(schedule),
            ["changed"] = changed,
        };
    }

    /// <summary>{"settings": {...}} as the settings file holds it, with profiles settled as startup does first.</summary>
    private static AppSettings SettingsOf(JsonObject request)
    {
        var settings = request["settings"].Deserialize<AppSettings>() ?? new AppSettings();
        settings.EnsureProfiles();
        return settings;
    }

    private static JsonArray Names(AppSettings s) =>
        new(s.Templates.Select(t => (JsonNode)t.Name).ToArray());

    private static JsonArray ScheduleIds(AppSettings s) =>
        new(s.Schedules.Select(x => (JsonNode)x.Id).ToArray());

    /// <summary>
    /// Runs EnsureTemplates twice, as two launches would, and returns what
    /// each reported, the lists as they came out, and the settings as a save
    /// would write them.
    /// </summary>
    private static JsonNode SettingsEnsureTemplates(JsonObject request)
    {
        var settings = SettingsOf(request);
        var first = settings.EnsureTemplates();
        var second = settings.EnsureTemplates();
        return new JsonObject
        {
            ["changed_first"] = first,
            ["changed_second"] = second,
            ["seeded"] = settings.TemplatesSeeded,
            ["templates"] = Names(settings),
            ["raw_templates"] = JsonSerializer.SerializeToNode(settings.Templates),
            ["schedules"] = ScheduleIds(settings),
            ["raw_schedules"] = JsonSerializer.SerializeToNode(settings.Schedules),
            ["saved"] = JsonSerializer.SerializeToNode(settings),
        };
    }

    /// <summary>{"settings", "id"} -> the schedules that start it, then what DeleteTemplate left.</summary>
    private static JsonNode SettingsDeleteTemplate(JsonObject request)
    {
        var settings = SettingsOf(request);
        var id = (string)request["id"]!;
        var usedBy = new JsonArray(settings.SchedulesUsing(id).Select(x => (JsonNode)x.Id).ToArray());
        var removed = settings.DeleteTemplate(id);
        return new JsonObject
        {
            ["used_by"] = usedBy,
            ["removed"] = removed,
            ["templates"] = Names(settings),
            ["schedules"] = ScheduleIds(settings),
        };
    }

    /// <summary>{"settings"} -> how many built-ins RestoreBuiltInTemplates added, and the names after.</summary>
    private static JsonNode SettingsRestore(JsonObject request)
    {
        var settings = SettingsOf(request);
        var added = settings.RestoreBuiltInTemplates();
        return new JsonObject { ["added"] = added, ["templates"] = Names(settings) };
    }

    /// <summary>{"settings", "template_id"} -> the name of the profile that template runs with.</summary>
    private static JsonNode SettingsProfileFor(JsonObject request)
    {
        var settings = SettingsOf(request);
        var template = settings.FindTemplate((string)request["template_id"]!)!;
        return new JsonObject { ["profile"] = settings.ProfileFor(template).Name };
    }

    /// <summary>{"settings", "wanted", "except_id"?} -> the name UniqueTemplateName hands back.</summary>
    private static JsonNode SettingsUniqueTemplateName(JsonObject request)
    {
        var settings = SettingsOf(request);
        var except = settings.FindTemplate((string?)request["except_id"]);
        return new JsonObject { ["name"] = settings.UniqueTemplateName((string)request["wanted"]!, except) };
    }

    private static JsonNode? Do(Action action)
    {
        action();
        return null;
    }
}
