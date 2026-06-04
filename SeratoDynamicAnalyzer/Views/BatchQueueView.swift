import SwiftUI
import UniformTypeIdentifiers
import AppKit

// MARK: - BatchQueueView
// Library-style track list with Kinetic Dark aesthetic.
// Includes search bar, column headers, drop zone, and file picker.

struct BatchQueueView: View {
    @ObservedObject var viewModel: BatchViewModel
    @State private var isTargeted: Bool = false
    @State private var searchText: String = ""

    private var filteredTracks: [TrackItem] {
        guard !searchText.isEmpty else { return viewModel.tracks }
        return viewModel.tracks.filter {
            $0.filename.localizedCaseInsensitiveContains(searchText)
        }
    }

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            VStack(spacing: 0) {
                // Search bar row
                SearchBarRow(text: $searchText)

                // Column header row
                ColumnHeaderRow()

                // Divider below headers
                Rectangle()
                    .fill(Color.kdOutline)
                    .frame(height: 1)

                // Track list or empty state
                if viewModel.tracks.isEmpty {
                    EmptyQueueView(isTargeted: isTargeted)
                } else {
                    List {
                        ForEach(filteredTracks) { item in
                            TrackRowView(item: item, viewModel: viewModel)
                                .listRowBackground(Color.kdBg)
                                .listRowInsets(EdgeInsets())
                                .listRowSeparatorTint(Color.kdOutline.opacity(0.6))
                        }
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                    .background(Color.kdBg)
                    .animation(.default, value: viewModel.tracks.count)
                }

                // Drop strip at bottom
                DropStripView(isScanning: viewModel.isScanning,
                              isTargeted: isTargeted,
                              onPickFiles: openFilePicker)
            }
            .onDrop(of: [UTType.fileURL], isTargeted: $isTargeted) { providers in
                for provider in providers {
                    _ = provider.loadObject(ofClass: URL.self) { url, _ in
                        guard let url = url else { return }
                        let resolved = url.standardizedFileURL
                        Task { @MainActor in
                            await viewModel.addDroppedURL(resolved)
                        }
                    }
                }
                return true
            }

            // FAB: add files (shown when queue has tracks)
            if !viewModel.tracks.isEmpty && !viewModel.isAnalyzing {
                AddFAB(action: openFilePicker)
                    .padding(.trailing, 20)
                    .padding(.bottom, 88)
            }
        }
        // Drop highlight overlay
        .overlay {
            if isTargeted {
                RoundedRectangle(cornerRadius: 0)
                    .stroke(Color.kdPrimary, lineWidth: 2)
                    .allowsHitTesting(false)
                    .animation(.easeInOut(duration: 0.15), value: isTargeted)
            }
        }
    }

    private func openFilePicker() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [
            UTType.mp3,
            UTType(filenameExtension: "aiff") ?? .audio,
            UTType(filenameExtension: "aif")  ?? .audio,
            UTType(filenameExtension: "wav")  ?? .audio,
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

// MARK: - SearchBarRow

private struct SearchBarRow: View {
    @Binding var text: String

    var body: some View {
        HStack(spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.kdMuted)
                TextField("", text: $text,
                          prompt: Text("SEARCH LIBRARY...")
                              .font(.kdLabel)
                              .foregroundColor(Color.kdMuted))
                    .font(.kdLabel)
                    .foregroundStyle(Color.kdOnSurface)
                    .textFieldStyle(.plain)
                if !text.isEmpty {
                    Button { text = "" } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 11))
                            .foregroundStyle(Color.kdMuted)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.kdSurface)
            .cornerRadius(6)
            .overlay(RoundedRectangle(cornerRadius: 6)
                .stroke(Color.kdOutline, lineWidth: 1))

            // Filter button
            Button {} label: {
                Image(systemName: "line.3.horizontal.decrease")
                    .font(.system(size: 13))
                    .foregroundStyle(Color.kdMuted)
                    .frame(width: 34, height: 34)
                    .background(Color.kdSurface)
                    .cornerRadius(6)
                    .overlay(RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.kdOutline, lineWidth: 1))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color.kdBg)
    }
}

// MARK: - ColumnHeaderRow

private struct ColumnHeaderRow: View {
    var body: some View {
        HStack(spacing: 0) {
            // Left edge indicator placeholder
            Rectangle()
                .fill(Color.clear)
                .frame(width: 3)

            Text("STAT")
                .font(.kdLabel)
                .foregroundStyle(Color.kdMuted)
                .frame(width: 90, alignment: .leading)
                .padding(.leading, 16)

            Text("TRACK NAME")
                .font(.kdLabel)
                .foregroundStyle(Color.kdMuted)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.leading, 8)

            HStack(spacing: 3) {
                Text("BPM")
                    .font(.kdLabel)
                    .foregroundStyle(Color.kdMuted)
                Image(systemName: "arrow.up.arrow.down")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(Color.kdMuted)
            }
            .frame(width: 88, alignment: .trailing)
            .padding(.trailing, 44)
        }
        .frame(height: 28)
        .background(Color.kdSurface)
    }
}

// MARK: - EmptyQueueView

private struct EmptyQueueView: View {
    var isTargeted: Bool

    var body: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: "waveform.badge.plus")
                .font(.system(size: 36, weight: .light))
                .foregroundStyle(isTargeted ? Color.kdPrimary : Color.kdOutline)
                .animation(.easeInOut(duration: 0.15), value: isTargeted)
            Text(isTargeted ? "DROP TO ADD TRACKS" : "NO TRACKS IN QUEUE")
                .font(.kdLabel)
                .foregroundStyle(isTargeted ? Color.kdPrimary : Color.kdMuted)
                .animation(.easeInOut(duration: 0.15), value: isTargeted)
            Text("Drop audio files or folders onto this window")
                .font(.kdBody)
                .foregroundStyle(Color.kdMuted.opacity(0.6))
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.kdBg)
    }
}

// MARK: - DropStripView

private struct DropStripView: View {
    var isScanning: Bool
    var isTargeted: Bool
    var onPickFiles: () -> Void

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .strokeBorder(
                        isTargeted ? Color.kdPrimary : Color.kdOutline,
                        style: StrokeStyle(lineWidth: isTargeted ? 1.5 : 1,
                                           dash: [6, 4])
                    )
                    .frame(height: 52)
                    .animation(.easeInOut(duration: 0.15), value: isTargeted)

                if isScanning {
                    HStack(spacing: 8) {
                        ProgressView()
                            .scaleEffect(0.65)
                            .tint(Color.kdPrimary)
                        Text("SCANNING FOLDER")
                            .font(.kdLabel)
                            .foregroundStyle(Color.kdMuted)
                    }
                } else {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.down.doc")
                            .font(.system(size: 13))
                            .foregroundStyle(isTargeted ? Color.kdPrimary : Color.kdMuted)
                        Text("DROP FILES OR FOLDERS")
                            .font(.kdLabel)
                            .foregroundStyle(isTargeted ? Color.kdPrimary : Color.kdMuted)
                    }
                    .animation(.easeInOut(duration: 0.15), value: isTargeted)
                }
            }

            Button("Choose Files…", action: onPickFiles)
                .buttonStyle(.plain)
                .font(.kdLabel)
                .foregroundStyle(Color.kdMuted)
                .padding(.vertical, 2)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color.kdBg)
        .overlay(alignment: .top) {
            Rectangle()
                .fill(Color.kdOutline)
                .frame(height: 1)
        }
    }
}

// MARK: - AddFAB

private struct AddFAB: View {
    var action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            Image(systemName: "plus")
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(Color.kdBg)
                .frame(width: 48, height: 48)
                .background(isHovered ? Color.kdPrimary.opacity(0.85) : Color.kdPrimary)
                .cornerRadius(12)
        }
        .buttonStyle(.plain)
        .shadow(color: Color.kdPrimary.opacity(0.3), radius: 8, x: 0, y: 4)
        .scaleEffect(isHovered ? 1.05 : 1.0)
        .animation(.easeInOut(duration: 0.15), value: isHovered)
        .onHover { isHovered = $0 }
        .accessibilityLabel("Add files to queue")
    }
}
