# Serato Dynamic Analyzer — Release Build Pipeline
#
# Usage:
#   make release        — Full pipeline: venv + build + sign + DMG
#   make deps           — Install build tools (uv via Homebrew if not present)
#   make bundle-python  — Embed Python venv + analyze.py into .app
#   make bundle-swift   — Build Swift app via xcodebuild (Release, ad-hoc signed)
#   make sign           — Ad-hoc code sign bottom-up (.so/.dylib → outer .app)
#   make dmg            — Package .app into distributable DMG
#   make clean          — Remove .app, derived data, .dmg (keeps venv cache)
#   make distclean      — Remove all of build/
#
# Python source: Homebrew Python 3.11 with --copies venv so the binary is a real
# copy (not a symlink). When the venv is moved inside the .app bundle, Python finds
# its pyvenv.cfg two levels above the binary and correctly activates site-packages.
# Works on the developer's Mac where Homebrew is installed. (Phase 2 dev build)

APP_NAME         := SeratoDynamicAnalyzer
APP              := build/$(APP_NAME).app
BUNDLE_RESOURCES := $(APP)/Contents/Resources
PYTHON_RUNTIME   := $(BUNDLE_RESOURCES)/python-runtime
SCRIPTS_DIR      := $(BUNDLE_RESOURCES)/scripts

# Homebrew Python 3.11 — provides a real subprocess-callable python binary.
# BeeWare Python.xcframework was tried but ships no bin/python3 executable.
# Auto-detect Homebrew prefix so both Apple Silicon (/opt/homebrew) and
# Intel (/usr/local) Macs work without manual edits (WR-07).
BREW_PREFIX := $(shell brew --prefix 2>/dev/null || echo /opt/homebrew)
BREW_PYTHON := $(BREW_PREFIX)/opt/python@3.11/bin/python3.11

# Xcode.app required for xcodebuild (CLT alone is insufficient)
DEVELOPER_DIR := /Applications/Xcode.app/Contents/Developer

# Entitlements (D-13: allow-unsigned-executable-memory + disable-library-validation)
ENTITLEMENTS := SeratoDynamicAnalyzer/Resources/SeratoDynamicAnalyzer.entitlements

.PHONY: release deps bundle-python bundle-swift sign dmg clean distclean publish

# ──────────────────────────────────────────────────────────────────────────────
# release: One-command pipeline (D-10)
# ──────────────────────────────────────────────────────────────────────────────
release: deps bundle-swift bundle-python sign dmg

# ──────────────────────────────────────────────────────────────────────────────
# deps: Install build tools — idempotent
# ──────────────────────────────────────────────────────────────────────────────
deps:
	which uv || brew install uv
	@test -f "$(BREW_PYTHON)" || (echo "ERROR: Homebrew Python 3.12 not found at $(BREW_PYTHON). Run: brew install python@3.11" && exit 1)
	@echo "deps OK — uv and Python 3.11 present"

# ──────────────────────────────────────────────────────────────────────────────
# Create relocatable venv with --copies so python3.12 binary is a real copy.
# A copied binary correctly resolves pyvenv.cfg when moved inside .app bundle.
# File rule — reruns only if venv dir does not exist.
# ──────────────────────────────────────────────────────────────────────────────
build/python-runtime/venv:
	mkdir -p build/python-runtime
	"$(BREW_PYTHON)" -m venv --copies build/python-runtime/venv
	uv pip install -r python/requirements.txt \
	    --python build/python-runtime/venv/bin/python3.11
	@echo "venv: Python 3.11 venv with all dependencies created"

# ──────────────────────────────────────────────────────────────────────────────
# bundle-python: Copy venv + analyze.py + library.py into .app Resources
# Layout: Resources/python-runtime/venv/bin/python3.11  (matches PythonBridge path)
#         Resources/scripts/analyze.py
#         Resources/scripts/library.py
# ──────────────────────────────────────────────────────────────────────────────
bundle-python: build/python-runtime/venv
	rm -rf "$(PYTHON_RUNTIME)"
	mkdir -p "$(PYTHON_RUNTIME)"
	cp -R build/python-runtime/venv "$(PYTHON_RUNTIME)/venv"
	mkdir -p "$(SCRIPTS_DIR)"
	cp python/analyze.py "$(SCRIPTS_DIR)/"
	cp python/library.py "$(SCRIPTS_DIR)/"
	chmod +x "$(PYTHON_RUNTIME)/venv/bin/python3.11"
	@echo "bundle-python: venv + analyze.py + library.py embedded"

# ──────────────────────────────────────────────────────────────────────────────
# bundle-swift: Build Swift app via xcodebuild, copy .app into build/
# ──────────────────────────────────────────────────────────────────────────────
bundle-swift:
	DEVELOPER_DIR="$(DEVELOPER_DIR)" xcodebuild clean build \
	    -project $(APP_NAME).xcodeproj \
	    -scheme $(APP_NAME) \
	    -configuration Release \
	    -derivedDataPath build/derived \
	    DEPLOYMENT_POSTPROCESSING=YES \
	    CODE_SIGN_IDENTITY=- \
	    2>&1 | tee build/xcodebuild.log | tail -20
	@if grep -q "BUILD SUCCEEDED" build/xcodebuild.log; then \
	    echo "BUILD SUCCEEDED"; \
	else \
	    echo "BUILD FAILED — see build/xcodebuild.log for details"; \
	    exit 1; \
	fi
	rm -rf "$(APP)"
	cp -R build/derived/Build/Products/Release/$(APP_NAME).app "$(APP)"
	@echo "bundle-swift: .app copied to $(APP)"

# ──────────────────────────────────────────────────────────────────────────────
# sign: Bottom-up ad-hoc code signing (D-12, D-13, CLAUDE.md signing order)
# Order: 1) all .so/.dylib in venv  2) outer .app with entitlements
# ──────────────────────────────────────────────────────────────────────────────
sign:
	find "$(PYTHON_RUNTIME)/venv" \( -name "*.dylib" -o -name "*.so" \) \
	    | xargs -I{} codesign --force --sign - --options runtime "{}"
	codesign --force --sign - --options runtime \
	    --entitlements "$(ENTITLEMENTS)" \
	    "$(APP)"
	@echo "sign: ad-hoc code signing complete"

# ──────────────────────────────────────────────────────────────────────────────
# dmg: Package .app into a distributable disk image
# ──────────────────────────────────────────────────────────────────────────────
dmg:
	hdiutil create \
	    -volname "Serato Dynamic Analyzer" \
	    -srcfolder "$(APP)" \
	    -ov -format UDZO \
	    "build/$(APP_NAME).dmg"
	@echo "dmg: build/$(APP_NAME).dmg created"

# ──────────────────────────────────────────────────────────────────────────────
# publish: One-command GitHub Release pipeline (D-02, D-03)
# Usage: git tag vX.Y.Z && make publish
# Requires: gh CLI authenticated (gh auth login), tag already created locally.
# Pushes tag to origin, then to both remotes via scripts/push-all.sh.
# ──────────────────────────────────────────────────────────────────────────────
publish: release
	@VERSION=$$(git describe --tags --abbrev=0) && \
	echo "Publishing release $$VERSION..." && \
	git push origin "$$VERSION" && \
	./scripts/push-all.sh && \
	gh release create "$$VERSION" \
	    "build/$(APP_NAME).dmg#$(APP_NAME)-$$VERSION.dmg" \
	    --title "Serato Dynamic Analyzer $$VERSION" \
	    --generate-notes \
	    --repo shatakaan/serato-dynamic-analyzer
	@echo "publish: GitHub Release published"

# ──────────────────────────────────────────────────────────────────────────────
# clean: Remove build artifacts (keeps venv cache at build/python-runtime/venv)
# ──────────────────────────────────────────────────────────────────────────────
clean:
	rm -rf "build/$(APP_NAME).app" build/derived "build/$(APP_NAME).dmg" build/xcodebuild.log
	@echo "clean: build artifacts removed (venv cache preserved)"

# ──────────────────────────────────────────────────────────────────────────────
# distclean: Full clean including venv cache
# ──────────────────────────────────────────────────────────────────────────────
distclean:
	rm -rf build/
	@echo "distclean: all build artifacts and cache removed"
