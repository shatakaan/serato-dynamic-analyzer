import SwiftUI

// MARK: - Kinetic Dark Color Tokens

extension Color {
    static let kdBg           = Color(kdHex: 0x131313)
    static let kdSurface      = Color(kdHex: 0x1C1B1B)
    static let kdSurfaceHigh  = Color(kdHex: 0x2A2A2A)
    static let kdSurfaceHigh2 = Color(kdHex: 0x353534)
    static let kdPrimary      = Color(kdHex: 0x00F0FF)  // neon cyan
    static let kdSecondary    = Color(kdHex: 0xFF4B89)  // hot pink
    static let kdTertiary     = Color(kdHex: 0xA2EF00)  // lime green
    static let kdOnSurface    = Color(kdHex: 0xE5E2E1)
    static let kdMuted        = Color(kdHex: 0x849495)
    static let kdOutline      = Color(kdHex: 0x3B494B)

    init(kdHex: UInt32) {
        let r = Double((kdHex >> 16) & 0xFF) / 255
        let g = Double((kdHex >> 8)  & 0xFF) / 255
        let b = Double( kdHex        & 0xFF) / 255
        self.init(red: r, green: g, blue: b)
    }
}

// MARK: - Kinetic Dark Typography

extension Font {
    static let kdBrand   = Font.system(size: 15, weight: .black)
    static let kdTitle   = Font.system(size: 18, weight: .bold)
    static let kdBody    = Font.system(size: 13, weight: .regular)
    static let kdLabel   = Font.system(size: 10, weight: .bold).smallCaps()
    static let kdMono    = Font.system(size: 12, weight: .medium, design: .monospaced)
    static let kdMonoLg  = Font.system(size: 16, weight: .bold,   design: .monospaced)
}

// MARK: - Kinetic Dark Status Colors

extension Color {
    static func kdStatusEdge(_ status: TrackStatus) -> Color {
        switch status {
        case .pending:   return Color.kdMuted.opacity(0.4)
        case .analyzing: return Color.kdPrimary
        case .done:      return Color.kdTertiary
        case .failed:    return Color.kdSecondary
        }
    }

    static func kdStatusText(_ status: TrackStatus) -> Color {
        switch status {
        case .pending:   return Color.kdMuted
        case .analyzing: return Color.kdPrimary
        case .done:      return Color.kdTertiary
        case .failed:    return Color.kdSecondary
        }
    }
}
