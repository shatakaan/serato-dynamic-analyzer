import SwiftUI

// MARK: - AppHeaderView
// Top brand bar: wavy logo + "GRID ENGINE" wordmark (left) + settings gear (right).
// Mimics the header from the Kinetic Dark design system across all screens.

struct AppHeaderView: View {
    var onSettings: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: 10) {
            // Wave / brand mark
            WavemarkIcon()
                .frame(width: 22, height: 18)
                .foregroundStyle(Color.kdPrimary)

            Text("GRID ENGINE")
                .font(.kdBrand)
                .foregroundStyle(Color.kdOnSurface)
                .tracking(1)

            Spacer()

            Button {
                onSettings?()
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 15, weight: .regular))
                    .foregroundStyle(Color.kdMuted)
            }
            .buttonStyle(.plain)
            .frame(width: 32, height: 32)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
        .background(Color.kdSurface)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(Color.kdOutline)
                .frame(height: 1)
        }
    }
}

// MARK: - WavemarkIcon
// Three horizontal wavy lines — the brand glyph from the Kinetic Dark designs.

private struct WavemarkIcon: View {
    var body: some View {
        Canvas { ctx, size in
            let w = size.width
            let h = size.height
            let gap = h / 4

            for i in 0..<3 {
                let y = gap + CGFloat(i) * gap
                var path = Path()
                path.move(to: CGPoint(x: 0, y: y))
                let amp = h * 0.09
                let half = w / 2
                path.addCurve(
                    to: CGPoint(x: half, y: y),
                    control1: CGPoint(x: w * 0.15, y: y - amp),
                    control2: CGPoint(x: w * 0.35, y: y + amp)
                )
                path.addCurve(
                    to: CGPoint(x: w, y: y),
                    control1: CGPoint(x: w * 0.65, y: y - amp),
                    control2: CGPoint(x: w * 0.85, y: y + amp)
                )
                ctx.stroke(path, with: .foreground, lineWidth: 1.8)
            }
        }
    }
}

#Preview {
    AppHeaderView()
        .frame(width: 700)
        .background(Color.kdBg)
}
