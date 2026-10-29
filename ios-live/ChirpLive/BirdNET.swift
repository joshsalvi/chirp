import Foundation

/// BirdNET 2.4 on the phone: the sound model (3 s of 48 kHz mono audio →
/// a score for each of 6,522 species) and the location model (latitude,
/// longitude and week → how likely each species is there that week).
/// Same models, inputs and scoring as the Chirp station (birdnetlib).
/// Models: BirdNET-Analyzer, CC BY-NC-SA 4.0 (K. Lisa Yang Center for
/// Conservation Bioacoustics and Chemnitz University of Technology).
final class BirdNET {
    struct Species: Hashable {
        let scientific: String
        let common: String
    }

    static let sampleRate = 48_000.0
    static let windowSamples = 144_000
    /// birdnetlib's default: species under this location score are left out.
    static let locationThreshold: Float = 0.03

    let species: [Species]
    private let sound: Interpreter
    private let location: Interpreter
    private let lock = NSLock()

    enum Failure: Error { case missing(String) }

    init(bundle: Bundle = Bundle(for: BirdNET.self)) throws {
        func path(_ name: String, _ ext: String) throws -> String {
            guard let p = bundle.path(forResource: name, ofType: ext) else { throw Failure.missing("\(name).\(ext)") }
            return p
        }
        let labels = try String(contentsOfFile: path("BirdNET_GLOBAL_6K_V2.4_Labels", "txt"), encoding: .utf8)
        species = labels.split(whereSeparator: \.isNewline).map { line in
            let parts = line.split(separator: "_", maxSplits: 1).map(String.init)
            return Species(scientific: parts.first ?? "", common: parts.count > 1 ? parts[1] : parts.first ?? "")
        }
        var options = Interpreter.Options()
        options.threadCount = 2
        sound = try Interpreter(modelPath: path("BirdNET_GLOBAL_6K_V2.4_Model_FP32", "tflite"), options: options)
        try sound.allocateTensors()
        location = try Interpreter(modelPath: path("BirdNET_GLOBAL_6K_V2.4_MData_Model_V2_FP16", "tflite"))
        try location.allocateTensors()
    }

    /// Scores (0...1) for one 3 s window of 48 kHz mono samples.
    func scores(_ window: [Float], sensitivity: Float = 1) throws -> [Float] {
        precondition(window.count == Self.windowSamples, "BirdNET needs 144,000 samples")
        lock.lock(); defer { lock.unlock() }
        try sound.copy(window.withUnsafeBufferPointer { Data(buffer: $0) }, toInputAt: 0)
        try sound.invoke()
        let logits = try sound.output(at: 0).data.toFloats()
        return logits.map { 1 / (1 + exp(-sensitivity * min(max($0, -15), 15))) }
    }

    /// Species likely at this place and week (indices into `species`).
    func likely(latitude: Double, longitude: Double, on date: Date = Date()) throws -> Set<Int> {
        let input: [Float] = [Float(latitude), Float(longitude), Float(Self.week48(date))]
        lock.lock(); defer { lock.unlock() }
        try location.copy(input.withUnsafeBufferPointer { Data(buffer: $0) }, toInputAt: 0)
        try location.invoke()
        let out = try location.output(at: 0).data.toFloats()
        return Set(out.indices.filter { out[$0] >= Self.locationThreshold })
    }

    /// BirdNET's 48-week year: ceil(day of year / days in year × 48).
    static func week48(_ date: Date, calendar: Calendar = .current) -> Int {
        let day = calendar.ordinality(of: .day, in: .year, for: date) ?? 1
        let days = calendar.range(of: .day, in: .year, for: date)?.count ?? 365
        return min(48, max(1, Int((Double(day) / Double(days) * 48).rounded(.up))))
    }
}

private extension Data {
    func toFloats() -> [Float] {
        withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
    }
}
