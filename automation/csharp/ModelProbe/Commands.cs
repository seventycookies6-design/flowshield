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
            _ => throw new ArgumentException($"unknown command '{cmd}'"),
        };
    }

    /// <summary>
    /// Runs SoftOverlayPolicy through a list of steps:
    /// {"op": "show"|"left"|"allow"|"back"|"reset", "app": "Discord", "at": seconds}.
    /// Each step's result is the method's return value, or null for void methods.
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
                "reset" => Do(policy.Reset),
                _ => throw new ArgumentException($"unknown soft op '{op}'"),
            };
            results.Add(result);
        }
        return new JsonObject { ["results"] = results };
    }

    /// <summary>
    /// Runs StudyTemplate.Normalize on {"template": {...}} and returns the
    /// template as it came out, with whether anything changed.
    /// </summary>
    private static JsonNode TemplateNormalize(JsonObject request)
    {
        var template = request["template"].Deserialize<StudyTemplate>()!;
        var changed = template.Normalize();
        return new JsonObject
        {
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
    /// date in "query", with the remembered dates as they came out.
    /// </summary>
    private static JsonNode ScheduleSkip(JsonObject request)
    {
        var schedule = ScheduleOf(request);
        foreach (var d in request["skip"]!.AsArray())
            schedule.Skip(DateTime.Parse((string)d!, CultureInfo.InvariantCulture));
        var queries = request["query"]!.AsArray()
            .Select(d => (JsonNode)schedule.IsSkipped(DateTime.Parse((string)d!, CultureInfo.InvariantCulture)))
            .ToArray();
        return new JsonObject
        {
            ["skipped"] = new JsonArray(schedule.SkippedDatesLocal
                .Select(d => (JsonNode)d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)).ToArray()),
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

    private static JsonNode? Do(Action action)
    {
        action();
        return null;
    }
}
