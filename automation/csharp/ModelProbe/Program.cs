using System.Text.Json.Nodes;
using FlowShield.ModelProbe;

// One JSON request on stdin, one JSON answer on stdout. Any failure is a
// non-zero exit with the exception on stderr, so a test can never pass on
// an answer that was never computed.
try
{
    var request = JsonNode.Parse(Console.In.ReadToEnd())!.AsObject();
    Console.Out.Write(Commands.Run(request).ToJsonString());
    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine(ex.ToString());
    return 1;
}
