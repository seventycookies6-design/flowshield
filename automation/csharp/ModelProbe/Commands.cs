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

    private static JsonNode? Do(Action action)
    {
        action();
        return null;
    }
}
