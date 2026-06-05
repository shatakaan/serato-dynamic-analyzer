import SwiftUI

// MARK: - LibraryTrackRow
// A single row in the library track table.
// Shows beatgrid source dot (none/serato/tool), filename, folder subtitle, duration, BPM.
// Analog: TrackRowView — same HStack layout, same color tokens, same 44pt row height.

struct LibraryTrackRow: View {
    let track: LibraryTrack

    var body: some View {
        HStack(spacing: 0) {
            // 8pt beatgrid dot — beatgrid source indicator (D-08)
            beatgridDot
                .frame(width: 28, alignment: .center)

            // Filename + folder subtitle
            VStack(alignment: .leading, spacing: 2) {
                Text(track.filename)
                    .font(.kdBody)
                    .foregroundStyle(Color.kdOnSurface)
                    .lineLimit(1)
                    .truncationMode(.middle)

                Text(track.url.deletingLastPathComponent().lastPathComponent)
                    .font(.system(size: 11))
                    .foregroundStyle(Color.kdMuted)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.leading, 4)

            // Duration (MM:SS)
            Text(durationText)
                .font(.kdMono)
                .foregroundStyle(Color.kdMuted)
                .frame(width: 56, alignment: .trailing)

            // BPM
            bpmText
                .frame(width: 72, alignment: .trailing)
                .padding(.trailing, 8)
        }
        .frame(minHeight: 44)
        .padding(.horizontal, 4)
    }

    // MARK: - Beatgrid dot

    private var beatgridDot: some View {
        Circle()
            .fill(dotColor)
            .frame(width: 8, height: 8)
    }

    private var dotColor: Color {
        switch track.beatgridSource {
        case .tool:   return Color.kdPrimary      // neon cyan — this-tool indicator (D-08)
        case .serato: return Color.kdWarning      // amber yellow — Serato-analyzed indicator
        case .none:   return Color.gray.opacity(0.35)
        }
    }

    // MARK: - Duration

    private var durationText: String {
        guard let sec = track.durationSec else { return "—:——" }
        let m = Int(sec) / 60
        let s = Int(sec) % 60
        return String(format: "%d:%02d", m, s)
    }

    // MARK: - BPM

    @ViewBuilder
    private var bpmText: some View {
        switch track.beatgridSource {
        case .tool:
            if let bpm = track.bpm {
                Text(String(format: "%.1f", bpm))
                    .font(.kdMono)
                    .foregroundStyle(Color.kdOnSurface)
            } else {
                Text("—")
                    .font(.kdMono)
                    .foregroundStyle(Color.kdMuted.opacity(0.4))
            }
        case .serato:
            if let bpm = track.bpm {
                Text(String(format: "%.1f", bpm))
                    .font(.kdMono)
                    .foregroundStyle(Color.kdMuted)
            } else {
                Text("—")
                    .font(.kdMono)
                    .foregroundStyle(Color.kdMuted.opacity(0.4))
            }
        case .none:
            Text("—")
                .font(.kdMono)
                .foregroundStyle(Color.kdMuted.opacity(0.4))
        }
    }
}
