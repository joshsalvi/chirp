import Foundation

/// Times and counts in plain words, like the web app (src/lite/ui.jsx).
enum Words {
    static func clock(_ d: Date?) -> String {
        guard let d else { return "" }
        return d.formatted(date: .omitted, time: .shortened)
    }

    /// "6:12 AM" → ("6:12", "AM"); 24-hour locales → ("06:12", "").
    static func clockParts(_ d: Date) -> (main: String, unit: String) {
        let t = clock(d).replacingOccurrences(of: "\u{202F}", with: " ")
        if let r = t.range(of: " ", options: .backwards) {
            let unit = String(t[r.upperBound...])
            if unit.allSatisfy({ $0.isLetter || $0 == "." }) { return (String(t[..<r.lowerBound]), unit) }
        }
        return (t, "")
    }

    static func when(_ d: Date?, now: Date = Date()) -> String {
        guard let d else { return "" }
        let cal = Calendar.current
        let days = cal.dateComponents([.day], from: cal.startOfDay(for: d), to: cal.startOfDay(for: now)).day ?? 0
        if days == 0 {
            let mins = Int(now.timeIntervalSince(d) / 60)
            if mins < 1 { return "Just now" }
            if mins < 60 { return "\(mins) min ago" }
            return "Today, \(clock(d))"
        }
        if days == 1 { return "Yesterday, \(clock(d))" }
        if days < 7 { return d.formatted(.dateTime.weekday(.wide)) + ", " + clock(d) }
        let sameYear = cal.component(.year, from: d) == cal.component(.year, from: now)
        return sameYear ? d.formatted(.dateTime.month(.abbreviated).day()) : d.formatted(.dateTime.month(.abbreviated).day().year())
    }

    static func longDate(_ d: Date?) -> String {
        d?.formatted(.dateTime.month(.wide).day().year()) ?? ""
    }

    static func greeting(_ d: Date = Date()) -> String {
        switch Calendar.current.component(.hour, from: d) {
        case ..<5: return "Good night"
        case ..<12: return "Good morning"
        case ..<17: return "Good afternoon"
        default: return "Good evening"
        }
    }

    static func count(_ n: Int, _ one: String, _ many: String? = nil) -> String {
        "\(n.formatted()) \(n == 1 ? one : (many ?? one + "s"))"
    }

    static func hour(_ h: Int) -> String {
        var c = DateComponents(); c.hour = h
        let d = Calendar.current.date(from: c) ?? Date()
        return d.formatted(.dateTime.hour())
    }

    /// "(c) Name, some rights reserved (CC BY)" → "Name, some rights reserved (CC BY)".
    static func credit(_ c: String) -> String {
        var t = c.trimmingCharacters(in: .whitespaces)
        for prefix in ["©", "(c)", "(C)", "Copyright"] where t.hasPrefix(prefix) {
            t = String(t.dropFirst(prefix.count)).trimmingCharacters(in: .whitespaces)
        }
        return t
    }
}
