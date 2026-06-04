#!/usr/bin/swift
// Generates AppIcon.icns for Serato Dynamic Analyzer.
// Run: swift scripts/generate_icon.swift
// Requires: macOS 13+

import AppKit
import Foundation

// MARK: - Icon Drawing

func drawIcon(size: Int) -> NSImage {
    let s = CGFloat(size)
    let img = NSImage(size: NSSize(width: s, height: s))

    img.lockFocus()
    guard let ctx = NSGraphicsContext.current?.cgContext else {
        img.unlockFocus()
        return img
    }

    // --- Background ---
    ctx.setFillColor(CGColor(red: 0.075, green: 0.075, blue: 0.075, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))

    let cx = s / 2
    let cy = s / 2

    // --- Circular tick marks (compass/clock style, muted teal) ---
    let tickColor = CGColor(red: 0.12, green: 0.30, blue: 0.30, alpha: 1.0)
    let tickCount = 12
    let outerR = s * 0.44
    let tickLen = s * 0.055
    let tickW   = max(1, s * 0.012)

    for i in 0..<tickCount {
        let angle = CGFloat(i) * (2 * .pi / CGFloat(tickCount)) - .pi / 2
        let x1 = cx + outerR * cos(angle)
        let y1 = cy + outerR * sin(angle)
        let x2 = cx + (outerR - tickLen) * cos(angle)
        let y2 = cy + (outerR - tickLen) * sin(angle)

        ctx.setStrokeColor(tickColor)
        ctx.setLineWidth(tickW)
        ctx.setLineCap(.round)
        ctx.move(to: CGPoint(x: x1, y: y1))
        ctx.addLine(to: CGPoint(x: x2, y: y2))
        ctx.strokePath()
    }

    // --- Vertical dashed beatgrid lines (muted teal) ---
    let dashColor = CGColor(red: 0.10, green: 0.28, blue: 0.28, alpha: 0.85)
    let dashW = max(1, s * 0.010)
    let gridY1 = cy - s * 0.22
    let gridY2 = cy + s * 0.22
    let gridOffsets: [CGFloat] = [-0.15, 0.15]
    let dashLen = s * 0.030
    let dashGap = s * 0.022

    for offset in gridOffsets {
        let gx = cx + s * offset
        ctx.setStrokeColor(dashColor)
        ctx.setLineWidth(dashW)
        ctx.setLineDash(phase: 0, lengths: [dashLen, dashGap])
        ctx.move(to: CGPoint(x: gx, y: gridY1))
        ctx.addLine(to: CGPoint(x: gx, y: gridY2))
        ctx.strokePath()
    }
    ctx.setLineDash(phase: 0, lengths: [])

    // --- Cyan ECG/waveform line ---
    // Flat → spike up → down → up → flat (heartbeat / beatgrid pulse)
    let cyanColor = CGColor(red: 0.0, green: 0.941, blue: 1.0, alpha: 1.0)
    let lineW = max(2, s * 0.028)

    let wLeft  = cx - s * 0.32
    let wRight = cx + s * 0.32
    let baseline = cy + s * 0.02

    // Key x positions
    let x0  = wLeft
    let x1  = cx - s * 0.16
    let x2  = cx - s * 0.06
    let x3  = cx
    let x4  = cx + s * 0.06
    let x5  = cx + s * 0.13
    let x6  = cx + s * 0.23
    let x7  = wRight

    // Key y positions
    let yBase  = baseline
    let yPeak  = cy - s * 0.20
    let yTrough = cy + s * 0.13
    let yMid   = cy - s * 0.07

    let path = CGMutablePath()
    path.move(to: CGPoint(x: x0, y: yBase))
    // Flat to pre-spike
    path.addLine(to: CGPoint(x: x1, y: yBase))
    // Spike up
    path.addLine(to: CGPoint(x: x2, y: yPeak))
    // Down through zero
    path.addLine(to: CGPoint(x: x3, y: yTrough))
    // Up to secondary peak
    path.addLine(to: CGPoint(x: x4, y: yMid))
    // Down then flat tail
    path.addLine(to: CGPoint(x: x5, y: yBase))
    path.addLine(to: CGPoint(x: x6, y: yBase))
    path.addLine(to: CGPoint(x: x7, y: yBase))

    ctx.addPath(path)
    ctx.setStrokeColor(cyanColor)
    ctx.setLineWidth(lineW)
    ctx.setLineCap(.round)
    ctx.setLineJoin(.round)
    ctx.strokePath()

    // Subtle cyan glow (wider, low opacity pass)
    ctx.addPath(path)
    ctx.setStrokeColor(CGColor(red: 0.0, green: 0.941, blue: 1.0, alpha: 0.18))
    ctx.setLineWidth(lineW * 3.5)
    ctx.strokePath()

    img.unlockFocus()
    return img
}

// MARK: - Save helpers

func savePNG(_ image: NSImage, to url: URL) {
    guard let tiff = image.tiffRepresentation,
          let rep  = NSBitmapImageRep(data: tiff),
          let png  = rep.representation(using: .png, properties: [:]) else {
        fputs("ERROR: could not encode PNG for \(url.lastPathComponent)\n", stderr)
        return
    }
    do {
        try png.write(to: url)
    } catch {
        fputs("ERROR: \(error)\n", stderr)
    }
}

// MARK: - Main

let fm = FileManager.default
let scriptDir = URL(fileURLWithPath: CommandLine.arguments[0])
    .deletingLastPathComponent()
let repoRoot = scriptDir.deletingLastPathComponent()

let iconsetDir = repoRoot
    .appendingPathComponent("SeratoDynamicAnalyzer.xcodeproj")
    .appendingPathComponent("AppIcon.iconset")   // temp location, moved to Resources later

// Use Resources dir directly
let outputDir = repoRoot
    .appendingPathComponent("SeratoDynamicAnalyzer")
    .appendingPathComponent("Resources")

let iconsetPath = outputDir.appendingPathComponent("AppIcon.iconset")

try? fm.createDirectory(at: iconsetPath, withIntermediateDirectories: true)

// Sizes required by iconutil
let sizes = [16, 32, 64, 128, 256, 512, 1024]
for sz in sizes {
    let img = drawIcon(size: sz)
    let filename = "icon_\(sz)x\(sz).png"
    savePNG(img, to: iconsetPath.appendingPathComponent(filename))
    print("  generated \(filename)")

    // @2x pairs (iconutil expects icon_NxN@2x.png for retina)
    if sz <= 512 {
        let img2x = drawIcon(size: sz * 2)
        let filename2x = "icon_\(sz)x\(sz)@2x.png"
        savePNG(img2x, to: iconsetPath.appendingPathComponent(filename2x))
        print("  generated \(filename2x)")
    }
}

// Build .icns using iconutil
let icnsPath = outputDir.appendingPathComponent("AppIcon.icns")
let proc = Process()
proc.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
proc.arguments = ["-c", "icns", "-o", icnsPath.path, iconsetPath.path]
try proc.run()
proc.waitUntilExit()

if proc.terminationStatus == 0 {
    print("✓ AppIcon.icns written to \(icnsPath.path)")
    // Clean up iconset
    try? fm.removeItem(at: iconsetPath)
} else {
    fputs("ERROR: iconutil failed (status \(proc.terminationStatus))\n", stderr)
}
