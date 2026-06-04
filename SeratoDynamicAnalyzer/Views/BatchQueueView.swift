import SwiftUI
import UniformTypeIdentifiers
import AppKit

// MARK: - BatchQueueView
// Primary content area: queue list, compact drop strip at bottom, "Choose Files..." button.
// Owns the onDrop multi-file handler and NSOpenPanel for secondary file selection.

struct BatchQueueView: View {
    @ObservedObject var viewModel: BatchViewModel
    @State private var isTargeted: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            // Queue list (or empty state)
            if viewModel.tracks.isEmpty {
                // Empty state
                VStack(spacing: 8) {
                    Spacer()
                    Text("No tracks in queue")
                        .font(.headline)
                    Text("Drop audio files or folders here to get started.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Spacer()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(viewModel.tracks) { item in
                        TrackRowView(item: item, viewModel: viewModel)
                    }
                }
                .listStyle(.plain)
                // Animate row insertions — NOT .id() which destroys lazy loading
                // (RESEARCH.md anti-patterns: no .id() on ForEach children)
                .animation(.default, value: viewModel.tracks.count)
            }

            // Compact drop strip pinned at bottom
            VStack(spacing: 6) {
                RoundedRectangle(cornerRadius: 8)
                    .strokeBorder(
                        isTargeted ? Color.accentColor : Color.secondary,
                        lineWidth: isTargeted ? 2 : 1
                    )
                    .frame(height: 80)
                    .overlay(
                        Group {
                            if viewModel.isScanning {
                                HStack(spacing: 8) {
                                    ProgressView()
                                        .scaleEffect(0.7)
                                    Text("Scanning folder…")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            } else {
                                VStack(spacing: 4) {
                                    Image(systemName: "arrow.down.doc")
                                        .font(.system(size: 20))
                                        .foregroundColor(.secondary)
                                    Text("Drop files or folders")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                        }
                    )
                    .animation(.easeInOut(duration: 0.15), value: isTargeted)

                Button("Choose Files…") {
                    openFilePicker()
                }
                .buttonStyle(.bordered)
                .font(.caption)
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 12)
            .background(Color(nsColor: .windowBackgroundColor))
        }
        // Drop handler — CRITICAL: loadObject must start synchronously for each provider
        // before this closure returns; the drop session closes on return.
        // (RESEARCH.md Pitfall 1 — never defer into Task.detached)
        .onDrop(of: [UTType.fileURL], isTargeted: $isTargeted) { providers in
            for provider in providers {
                _ = provider.loadObject(ofClass: URL.self) { url, _ in
                    guard let url = url else { return }
                    // WR-06: standardizedFileURL converts file-reference URLs
                    // (file:///.file/id=…) to regular path-based URLs.
                    let resolved = url.standardizedFileURL
                    Task { @MainActor in
                        await viewModel.addDroppedURL(resolved)
                    }
                }
            }
            return true
        }
    }

    // MARK: - NSOpenPanel file picker
    // fileImporter cannot select directories — use NSOpenPanel with canChooseDirectories = true.
    // (RESEARCH.md Open Question 4 — NSOpenPanel is the correct approach)
    private func openFilePicker() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [
            UTType.mp3,
            UTType(filenameExtension: "aiff") ?? .audio,
            UTType(filenameExtension: "aif") ?? .audio,
            UTType(filenameExtension: "wav") ?? .audio,
        ]
        if panel.runModal() == .OK {
            for url in panel.urls {
                Task { @MainActor in
                    await viewModel.addDroppedURL(url.standardizedFileURL)
                }
            }
        }
    }
}
