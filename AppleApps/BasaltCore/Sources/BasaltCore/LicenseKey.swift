import Foundation

public enum LicenseKey {
  public static let alphabet = Array("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
  public static func normalize(_ input: String) -> String {
    input.uppercased().replacingOccurrences(
      of:
        "[\\x{0009}-\\x{000D} _\\x{00A0}\\x{1680}\\x{2000}-\\x{200A}\\x{2028}\\x{2029}\\x{202F}\\x{205F}\\x{3000}\\x{FEFF}]",
      with: "", options: .regularExpression)
  }
  public static func hasShape(_ value: String) -> Bool {
    value.range(of: "^FS(?:-[0-9A-HJKMNP-TV-Z]{4}){4}$", options: .regularExpression) != nil
  }
  /// Typo check only; never grants access without the server's verdict.
  public static func isWellFormed(_ input: String) -> Bool {
    let key = normalize(input)
    guard hasShape(key) else { return false }
    let body = Array(key.dropFirst(3).filter { $0 != "-" })
    let sum = (0..<15).reduce(0) { $0 + alphabet.firstIndex(of: body[$1])! * (2 * $1 + 1) }
    return body[15] == alphabet[sum % alphabet.count]
  }
}
public enum DeepLink {
  public static let scheme = "flowshield"
  public static func parseActivationKey(_ link: String) -> String? {
    guard let url = URLComponents(string: trimmed(link)), url.scheme?.lowercased() == scheme else {
      return nil
    }
    let action = ((url.host ?? "") + url.path).trimmingCharacters(
      in: CharacterSet(charactersIn: "/"))
    guard action.lowercased() == "activate" else { return nil }
    // Windows uses the last key parameter, shape only (checksum is the server's job).
    let key = url.queryItems?.last { $0.name.lowercased() == "key" }?.value.map {
      trimmed($0).uppercased()
    }
    return key.flatMap { LicenseKey.hasShape($0) ? $0 : nil }
  }
  public static func findLink(_ args: [String]) -> String? {
    args.first { $0.lowercased().hasPrefix(scheme + ":") }
  }
}
