import Foundation

// MARK: - BridgeError

enum BridgeError: Error {
    case bundlePathUnavailable
    case pythonBinaryNotFound(path: String)
    case analyzeScriptNotFound
    case workerNotRunning
}

// MARK: - PythonBridge actor

actor PythonBridge {
    private var process: Process?
    private var stdinPipe: Pipe = Pipe()
    private let stdoutPipe: Pipe = Pipe()
    private let stderrPipe: Pipe = Pipe()
    private var isWorkerRunning: Bool = false

    // MARK: Worker startup

    func startWorker() async throws {
        let pythonURL = try pythonBinaryURL()
        let scriptURL = try analyzeScriptURL()

        let p = Process()
        p.executableURL = pythonURL
        p.arguments = ["-u", scriptURL.path, "--worker"]

        // Create fresh stdinPipe; MUST be assigned before p.run() (Pitfall 1 prevention)
        stdinPipe = Pipe()
        p.standardInput = stdinPipe
        p.standardOutput = stdoutPipe
        p.standardError = stderrPipe

        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        // PYTHONHOME is intentionally NOT set: the --copies venv binary resolves
        // its own home from its executable path via pyvenv.cfg — setting PYTHONHOME
        // would override that and break stdlib discovery.
        p.environment = env

        p.terminationHandler = { [weak self] proc in
            Task { await self?.handleCrash(exitCode: proc.terminationStatus) }
        }

        // Drain stderr asynchronously — prevents pipe buffer fill blocking Python (Pitfall 5)
        Task {
            let handle = stderrPipe.fileHandleForReading
            do {
                for try await line in handle.bytes.lines {
                    print("[python stderr]", line)
                }
            } catch {}
        }

        try p.run()
        process = p
        isWorkerRunning = true
    }

    // MARK: Crash handler

    private func handleCrash(exitCode: Int32) {
        isWorkerRunning = false
        process = nil
        // Next analyze() call will auto-restart the worker
    }

    // MARK: Wait for ready signal (called once after startWorker)

    func waitForReady(timeout: TimeInterval = 30) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        let handle = stdoutPipe.fileHandleForReading
        do {
            for try await line in handle.bytes.lines {
                if let event = parseEvent(line), case .ready = event {
                    return true
                }
                if Date() > deadline { return false }
            }
        } catch {}
        return false
    }

    // MARK: Send analysis request + stream events

    func analyzeStream(filePath: String, bpmMin: Int, bpmMax: Int, dryRun: Bool) -> AsyncStream<WorkerEvent> {
        AsyncStream { continuation in
            Task {
                // Restart worker if it crashed
                if !isWorkerRunning {
                    try? await startWorker()
                    // Wait for ready after restart
                    let _ = await waitForReady(timeout: 30)
                }
                // Build JSON-Lines request and write to stdin
                let request: [String: Any] = [
                    "file": filePath,
                    "bpm_min": bpmMin,
                    "bpm_max": bpmMax,
                    "dry_run": dryRun,
                ]
                if let data = try? JSONSerialization.data(withJSONObject: request),
                   let line = String(data: data, encoding: .utf8) {
                    let payload = (line + "\n").data(using: .utf8)!
                    stdinPipe.fileHandleForWriting.write(payload)
                }
                // Read JSONL events until result or error (terminal events)
                let handle = stdoutPipe.fileHandleForReading
                do {
                    for try await rawLine in handle.bytes.lines {
                        guard let event = parseEvent(rawLine) else { continue }
                        continuation.yield(event)
                        if case .result = event { break }
                        if case .error = event { break }
                    }
                } catch {}
                continuation.finish()
            }
        }
    }

    // MARK: JSONL event parser

    func parseEvent(_ line: String) -> WorkerEvent? {
        guard let data = line.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type_ = json["type"] as? String else { return nil }
        switch type_ {
        case "ready":
            return .ready
        case "progress":
            return .progress(
                file: json["file"] as? String ?? "",
                pct: json["pct"] as? Int ?? 0
            )
        case "result":
            return .result(AnalysisResult(json: json))
        case "error":
            return .error(
                file: json["file"] as? String ?? "",
                message: json["msg"] as? String ?? "Unknown error"
            )
        default:
            return nil
        }
    }

    // MARK: Bundle path helpers

    func pythonBinaryURL() throws -> URL {
        guard let resourcePath = Bundle.main.resourcePath else {
            throw BridgeError.bundlePathUnavailable
        }
        // Path matches Makefile bundle-python target:
        // Resources/python-runtime/venv/bin/python3.11
        // The venv is built with --copies so this is a real executable, not a symlink.
        let pythonURL = URL(fileURLWithPath: resourcePath)
            .appendingPathComponent("python-runtime")
            .appendingPathComponent("venv")
            .appendingPathComponent("bin")
            .appendingPathComponent("python3.11")
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            throw BridgeError.pythonBinaryNotFound(path: pythonURL.path)
        }
        return pythonURL
    }

    func analyzeScriptURL() throws -> URL {
        guard let path = Bundle.main.path(forResource: "analyze", ofType: "py",
                                          inDirectory: "scripts") else {
            throw BridgeError.analyzeScriptNotFound
        }
        return URL(fileURLWithPath: path)
    }
}
