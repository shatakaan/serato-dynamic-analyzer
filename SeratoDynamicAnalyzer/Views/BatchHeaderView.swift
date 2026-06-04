import SwiftUI

// MARK: - BatchHeaderView
// Sub-header below AppHeaderView: batch progress, BPM range controls, Analyze All CTA.

struct BatchHeaderView: View {
    @ObservedObject var viewModel: BatchViewModel

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .center, spacing: 16) {

                // Progress section (only when tracks are queued)
                if viewModel.totalCount > 0 {
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Text("\(viewModel.completedCount)")
                                .font(.kdMonoLg)
                                .foregroundStyle(Color.kdPrimary)
                            Text("/ \(viewModel.totalCount)")
                                .font(.kdMono)
                                .foregroundStyle(Color.kdMuted)
                            Text("TRACKS")
                                .font(.kdLabel)
                                .foregroundStyle(Color.kdMuted)
                        }
                        KdProgressBar(value: Double(viewModel.completedCount),
                                      total: Double(max(1, viewModel.totalCount)))
                            .animation(.linear(duration: 0.3), value: viewModel.completedCount)
                    }
                    .frame(minWidth: 180)
                }

                Spacer()

                // BPM range
                HStack(spacing: 6) {
                    Text("BPM")
                        .font(.kdLabel)
                        .foregroundStyle(Color.kdMuted)

                    KdStepper(value: $viewModel.globalBpmMin,
                              range: 20...(viewModel.globalBpmMax - 1))
                        .disabled(viewModel.isAnalyzing)

                    Text("\(viewModel.globalBpmMin)")
                        .font(.kdMono)
                        .foregroundStyle(Color.kdOnSurface)
                        .frame(minWidth: 30, alignment: .trailing)

                    Text("–")
                        .font(.kdMono)
                        .foregroundStyle(Color.kdMuted)

                    Text("\(viewModel.globalBpmMax)")
                        .font(.kdMono)
                        .foregroundStyle(Color.kdOnSurface)
                        .frame(minWidth: 30, alignment: .leading)

                    KdStepper(value: $viewModel.globalBpmMax,
                              range: (viewModel.globalBpmMin + 1)...300)
                        .disabled(viewModel.isAnalyzing)
                }

                // Dry run toggle
                KdToggle(label: "DRY RUN", isOn: $viewModel.isDryRun)
                    .disabled(viewModel.isAnalyzing)

                // Analyze CTA
                Button {
                    viewModel.startBatch()
                } label: {
                    HStack(spacing: 6) {
                        if viewModel.isAnalyzing {
                            ProgressView()
                                .scaleEffect(0.65)
                                .tint(Color.kdBg)
                        } else {
                            Image(systemName: "waveform")
                                .font(.system(size: 12, weight: .bold))
                        }
                        Text(viewModel.isAnalyzing ? "ANALYZING" : "ANALYZE ALL")
                            .font(.kdLabel)
                            .tracking(0.5)
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(viewModel.canStartBatch ? Color.kdPrimary : Color.kdOutline)
                    .foregroundStyle(viewModel.canStartBatch ? Color.kdBg : Color.kdMuted)
                    .cornerRadius(6)
                }
                .buttonStyle(.plain)
                .disabled(!viewModel.canStartBatch)
                .animation(.easeInOut(duration: 0.15), value: viewModel.canStartBatch)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(Color.kdBg)

            Rectangle()
                .fill(Color.kdOutline)
                .frame(height: 1)
        }
    }
}

// MARK: - KdProgressBar

private struct KdProgressBar: View {
    var value: Double
    var total: Double

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.kdSurfaceHigh)
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.kdPrimary)
                    .frame(width: geo.size.width * (value / total))
            }
        }
        .frame(height: 3)
        .frame(minWidth: 120)
    }
}

// MARK: - KdStepper (Int-specific +/- arrows)

private struct KdStepper: View {
    @Binding var value: Int
    var range: ClosedRange<Int>

    var body: some View {
        HStack(spacing: 0) {
            Button {
                if value > range.lowerBound { value -= 1 }
            } label: {
                Image(systemName: "minus")
                    .font(.system(size: 9, weight: .bold))
            }
            .buttonStyle(.plain)
            .frame(width: 18, height: 22)
            .background(Color.kdSurfaceHigh)

            Rectangle()
                .fill(Color.kdOutline)
                .frame(width: 1, height: 22)

            Button {
                if value < range.upperBound { value += 1 }
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 9, weight: .bold))
            }
            .buttonStyle(.plain)
            .frame(width: 18, height: 22)
            .background(Color.kdSurfaceHigh)
        }
        .foregroundStyle(Color.kdMuted)
        .cornerRadius(4)
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.kdOutline, lineWidth: 1))
    }
}

// MARK: - KdToggle

private struct KdToggle: View {
    var label: String
    @Binding var isOn: Bool

    var body: some View {
        Button { isOn.toggle() } label: {
            HStack(spacing: 5) {
                RoundedRectangle(cornerRadius: 3)
                    .fill(isOn ? Color.kdPrimary.opacity(0.2) : Color.kdSurfaceHigh)
                    .overlay(
                        RoundedRectangle(cornerRadius: 3)
                            .stroke(isOn ? Color.kdPrimary : Color.kdOutline, lineWidth: 1)
                    )
                    .overlay(
                        Image(systemName: isOn ? "checkmark" : "")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundStyle(Color.kdPrimary)
                    )
                    .frame(width: 16, height: 16)
                Text(label)
                    .font(.kdLabel)
                    .foregroundStyle(isOn ? Color.kdPrimary : Color.kdMuted)
            }
        }
        .buttonStyle(.plain)
        .animation(.easeInOut(duration: 0.1), value: isOn)
    }
}
