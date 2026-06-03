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
    private var stdinPipe:  Pipe = Pipe()
    private var stdoutPipe: Pipe = Pipe()   // var: recreated on each restart
    private var stderrPipe: Pipe = Pipe()   // var: recreated on each restart
    private var isWorkerRunning: Bool = false

    // MARK: Worker startup

    func startWorker() async throws {
        let pythonURL = try pythonBinaryURL()
        let scriptURL = try analyzeScriptURL()

        let p = Process()
        p.executableURL = pythonURL
        p.arguments = ["-u", scriptURL.path, "--worker"]

        // Create fresh pipes on every (re)start so stale read loops see EOF
        // after a crash rather than blocking forever (CR-01).
        stdinPipe  = Pipe()
        stdoutPipe = Pipe()
        stderrPipe = Pipe()
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
        // Close the write end of stdout so any in-flight bytes.lines reader
        // sees EOF and unblocks rather than hanging forever (CR-01).
        try? stdoutPipe.fileHandleForWriting.close()
        process = nil
        // Next analyze() call will auto-restart the worker
    }

    // MARK: Wait for ready signal (called once after startWorker)

    func waitForReady(timeout: TimeInterval = 30) async -> Bool {
        let handle = stdoutPipe.fileHandleForReading
        // Race the line-reading loop against a deadline task (CR-02).
        // Without this race the deadline check inside the loop only fires when a
        // new line arrives — a silent Python startup failure (import error, crash
        // before "ready", buffering) suspends the await forever.
        return await withTaskGroup(of: Bool.self) { group in
            group.addTask {
                do {
                    for try await line in handle.bytes.lines {
                        if let event = self.parseEvent(line), case .ready = event {
                            return true
                        }
                    }
                } catch {}
                return false
            }
            group.addTask {
                try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
                return false
            }
            let result = await group.next() ?? false
            group.cancelAll()
            return result
        }
    }

    // MARK: Send analysis request + stream events

    func analyzeStream(filePath: String, bpmMin: Int, bpmMax: Int, dryRun: Bool) -> AsyncStream<WorkerEvent> {
        AsyncStream { continuation in
            Task {
                // Restart worker if it crashed
                if !isWorkerRunning {
                    // Propagate startWorker() failures rather than silently
                    // discarding them (WR-01): a missing Python binary or
                    // bundle misconfiguration must surface as an error event,
                    // not leave the continuation hanging waiting for output
                    // that will never arrive.
                    do {
                        try await startWorker()
                    } catch {
                        continuation.yield(.error(file: filePath,
                            message: "Failed to restart Python worker: \(error)"))
                        continuation.finish()
                        return
                    }
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
                // Surface serialization failure as an error event (WR-04).
                // Silent if-let would skip the write, leaving Python's read loop
                // hanging and AnalysisViewModel.isRunning stuck true forever.
                guard let data = try? JSONSerialization.data(withJSONObject: request),
                      let line = String(data: data, encoding: .utf8) else {
                    continuation.yield(.error(file: filePath,
                        message: "Failed to serialize analysis request"))
                    continuation.finish()
                    return
                }
                let payload = (line + "\n").data(using: .utf8)!
                stdinPipe.fileHandleForWriting.write(payload)
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

    nonisolated func parseEvent(_ line: String) -> WorkerEvent? {
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
        // Resources/python-runtime/venv/bin/python3.12
        // The venv is built with --copies so this is a real executable, not a symlink.
        let pythonURL = URL(fileURLWithPath: resourcePath)
            .appendingPathComponent("python-runtime")
            .appendingPathComponent("venv")
            .appendingPathComponent("bin")
            .appendingPathComponent("python3.12")
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
