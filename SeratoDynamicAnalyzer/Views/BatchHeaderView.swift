import SwiftUI

// MARK: - BatchHeaderView
// Sticky header above the queue list: batch progress counter, linear ProgressView,
// global BPM steppers, Dry Run toggle, and the "Analyze All" CTA.

struct BatchHeaderView: View {
    @ObservedObject var viewModel: BatchViewModel

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .center, spacing: 16) {
                // Progress counter + linear progress bar (shown when tracks are in queue)
                if viewModel.totalCount > 0 {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(viewModel.completedCount) of \(viewModel.totalCount) tracks complete")
                            .font(.caption)
                            .foregroundColor(Color(nsColor: .secondaryLabelColor))
                        ProgressView(value: Double(viewModel.completedCount),
                                     total: Double(max(1, viewModel.totalCount)))
                            .progressViewStyle(.linear)
                            .tint(.accentColor)
                            .animation(.linear(duration: 0.3), value: viewModel.completedCount)
                            .accessibilityValue("\(viewModel.completedCount) of \(viewModel.totalCount) tracks complete")
                    }
                    .frame(minWidth: 200)
                }

                Spacer()

                // Global BPM range controls
                HStack(spacing: 4) {
                    Text("BPM")
                        .font(.caption)
                        .foregroundColor(Color(nsColor: .secondaryLabelColor))
                    Stepper("", value: $viewModel.globalBpmMin,
                            in: 20...(viewModel.globalBpmMax - 1))
                        .labelsHidden()
                    Text("\(viewModel.globalBpmMin)")
                        .font(.body)
                        .frame(minWidth: 36)
                    Text("–")
                    Text("\(viewModel.globalBpmMax)")
                        .font(.body)
                        .frame(minWidth: 36)
                    Stepper("", value: $viewModel.globalBpmMax,
                            in: (viewModel.globalBpmMin + 1)...300)
                        .labelsHidden()
                }
                .disabled(viewModel.isAnalyzing)

                Toggle("Dry Run", isOn: $viewModel.isDryRun)
                    .disabled(viewModel.isAnalyzing)

                Button(viewModel.isAnalyzing ? "Analyzing…" : "Analyze All") {
                    viewModel.startBatch()
                }
                .buttonStyle(.borderedProminent)
                .disabled(!viewModel.canStartBatch)
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 16)
            .background(Color(nsColor: .controlBackgroundColor))

            // Worker warmup hint — shown while Python is loading libraries
            if viewModel.workerReadyCount == 0 && !viewModel.isAnalyzing {
                Text("Starting analysis engine…")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 24)
                    .padding(.bottom, 4)
            }

            Divider()
        }
    }
}
