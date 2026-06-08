import Foundation

// MARK: - BridgeError

enum BridgeError: Error {
    case bundlePathUnavailable
    case pythonBinaryNotFound(path: String)
    case analyzeScriptNotFound
    case workerNotRunning
}

// MARK: - LibraryEvent

enum LibraryEvent {
    case crates([SeratoCrate])
    case cratesFile(String)    // path to temp JSON file (avoids pipe buffer overflow)
    case tracks([LibraryTrack])
    case error(String)
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
                // hanging and the track item stuck in Analyzing state forever.
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

    // MARK: Pipe reading helper

    /// Wraps FileHandle.readabilityHandler in an AsyncStream<String> yielding
    /// newline-delimited lines. Use this instead of FileHandle.bytes.lines for
    /// library IPC: bytes.lines leaves a stale DispatchSource after cancellation
    /// that silently consumes subsequent pipe data (CR-03 root cause).
    nonisolated func pipeLines(handle: FileHandle) -> AsyncStream<String> {
        AsyncStream { continuation in
            var buffer = ""
            handle.readabilityHandler = { fh in
                let data = fh.availableData
                guard !data.isEmpty else {
                    handle.readabilityHandler = nil
                    continuation.finish()
                    return
                }
                guard let chunk = String(data: data, encoding: .utf8) else { return }
                buffer += chunk
                while let newlineRange = buffer.range(of: "\n") {
                    let line = String(buffer[buffer.startIndex..<newlineRange.lowerBound])
                    buffer.removeSubrange(buffer.startIndex...newlineRange.lowerBound)
                    continuation.yield(line)
                }
            }
            continuation.onTermination = { _ in
                handle.readabilityHandler = nil
            }
        }
    }

    // MARK: Library Commands (Plan 04-02)

    /// Send list_crates command and return the crate tree.
    /// Uses pipeLines (readabilityHandler-based) to avoid bytes.lines DispatchSource
    /// stale-reader bug on IPC pipes (CR-03).
    func listCrates() async -> [SeratoCrate] {
        if !isWorkerRunning {
            do { try await startWorker() } catch { return [] }
        }
        let request: [String: Any] = ["cmd": "list_crates"]
        guard let data = try? JSONSerialization.data(withJSONObject: request),
              let line = String(data: data, encoding: .utf8) else { return [] }
        stdinPipe.fileHandleForWriting.write((line + "\n").data(using: .utf8)!)

        let handle = stdoutPipe.fileHandleForReading
        for await rawLine in pipeLines(handle: handle) {
            if let evt = parseEvent(rawLine), case .ready = evt { continue }
            guard let parsed = parseLibraryEvent(rawLine) else { continue }
            switch parsed {
            case .crates(let tree): return tree
            case .cratesFile(let path):
                if let fileData = try? Data(contentsOf: URL(fileURLWithPath: path)),
                   let rawTree = try? JSONSerialization.jsonObject(with: fileData) as? [[String: Any]] {
                    try? FileManager.default.removeItem(atPath: path)
                    return rawTree.map { SeratoCrate(json: $0) }
                }
                return []
            case .error: return []
            default: continue
            }
        }
        return []
    }

    /// Send list_tracks command and return tracks for the given crate path.
    /// Same pipeLines strategy as listCrates (CR-03).
    func listTracks(crate: String) async -> [LibraryTrack] {
        if !isWorkerRunning {
            try? await startWorker()
        }
        let request: [String: Any] = ["cmd": "list_tracks", "crate": crate]
        guard let data = try? JSONSerialization.data(withJSONObject: request),
              let line = String(data: data, encoding: .utf8) else { return [] }
        stdinPipe.fileHandleForWriting.write((line + "\n").data(using: .utf8)!)

        let handle = stdoutPipe.fileHandleForReading
        for await rawLine in pipeLines(handle: handle) {
            if let evt = parseEvent(rawLine), case .ready = evt { continue }
            guard let parsed = parseLibraryEvent(rawLine) else { continue }
            switch parsed {
            case .tracks(let list): return list
            case .error:            return []
            default:                continue
            }
        }
        return []
    }

    // MARK: Library JSONL event parser

    nonisolated func parseLibraryEvent(_ line: String) -> LibraryEvent? {
        guard let data = line.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type_ = json["type"] as? String else { return nil }
        switch type_ {
        case "crates":
            let rawTree = json["tree"] as? [[String: Any]] ?? []
            return .crates(rawTree.map { SeratoCrate(json: $0) })
        case "crates_file":
            return .cratesFile(json["path"] as? String ?? "")
        case "tracks":
            let rawList = json["tracks"] as? [[String: Any]] ?? []
            return .tracks(rawList.map { LibraryTrack(json: $0) })
        case "error":
            return .error(json["msg"] as? String ?? "Unknown library error")
        default:
            return nil
        }
    }

    // MARK: Terminate (D-11 per-track cancel)

    /// Terminate the underlying Python process for this worker slot.
    /// actor-isolated (not nonisolated) — caller awaits; cancel is not latency-critical.
    /// The existing terminationHandler fires handleCrash(), which sets isWorkerRunning = false
    /// so the next analyzeStream() call auto-restarts the worker (Phase 2 crash-recovery pattern).
    func terminate() {
        process?.terminate()
    }

    // MARK: Bundle path helpers

    func pythonBinaryURL() throws -> URL {
        guard let resourcePath = Bundle.main.resourcePath else {
            throw BridgeError.bundlePathUnavailable
        }
        // Path matches Makefile bundle-python target:
        // Resources/python-runtime/venv/bin/python3.11
        // The venv is built with --copies so this is a real executable, not a symlink.
        // python@3.11 is the installed Homebrew version; upgrade to 3.12 when available.
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
