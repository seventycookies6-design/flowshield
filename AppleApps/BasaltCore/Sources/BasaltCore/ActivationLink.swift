import Foundation

public enum ActivationLink {
  /// A link only prefills the confirmation UI. It never starts a network request.
  public static func key(from text: String) -> String? {
    guard let c = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
      c.scheme?.lowercased() == "flowshield",
      ((c.host ?? "") + c.path).trimmingCharacters(in: CharacterSet(charactersIn: "/")).lowercased() == "activate",
      let key = c.queryItems?.last(where: { $0.name.lowercased() == "key" })?.value?
        .trimmingCharacters(in: .whitespacesAndNewlines).uppercased(),
      key.range(of: "^FS-[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){3}$", options: .regularExpression) != nil
    else { return nil }
    return key
  }
}
