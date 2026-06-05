import SwiftUI

// MARK: - LibraryEmptyStateView
// Shown in the Library tab when ~/Music/_Serato_/ does not exist.
// D-06: No file picker — just instructions to open Serato DJ Pro once.

struct LibraryEmptyStateView: View {
    var body: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: "music.note.list")
                .font(.system(size: 40, weight: .light))
                .foregroundStyle(Color.kdOutline)

            Text("No Serato Library Found")
                .font(.kdTitle)
                .foregroundStyle(Color.kdOnSurface)

            Text("Open Serato DJ Pro once to create your library at ~/Music/_Serato_/.")
                .font(.kdBody)
                .foregroundStyle(Color.kdMuted)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 320)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.kdBg)
    }
}
