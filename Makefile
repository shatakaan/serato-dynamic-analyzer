# Serato Dynamic Analyzer — Release Build Pipeline
#
# Usage:
#   make release        — Full pipeline: download + venv + build + sign + DMG
#   make deps           — Install build tools (uv via Homebrew if not present)
#   make bundle-python  — Embed Python.framework + venv + analyze.py into .app
#   make bundle-swift   — Build Swift app via xcodebuild (Release, ad-hoc signed)
#   make sign           — Ad-hoc code sign bottom-up (.so/.dylib → framework → .app)
#   make dmg            — Package .app into distributable DMG
#   make clean          — Remove .app, derived data, .dmg (keeps BeeWare cache + venv)
#   make distclean      — Remove all of build/

APP_NAME         := SeratoDynamicAnalyzer
APP              := build/$(APP_NAME).app
BUNDLE_RESOURCES := $(APP)/Contents/Resources
PYTHON_RUNTIME   := $(BUNDLE_RESOURCES)/python-runtime
SCRIPTS_DIR      := $(BUNDLE_RESOURCES)/scripts

# BeeWare Python 3.12-b8 (macOS, pre-relocated — no install_name_tool needed)
BEEWARE_URL := https://github.com/beeware/Python-Apple-support/releases/download/3.12-b8/Python-3.12-macOS-support.b8.tar.gz
BEEWARE_TAR := build/cache/Python-3.12-macOS-support.b8.tar.gz

# Xcode.app is required for xcodebuild (CLT alone is insufficient — see STATE.md D-02-03)
DEVELOPER_DIR := /Applications/Xcode.app/Contents/Developer

# Entitlements file path (D-13: allow-unsigned-executable-memory + disable-library-validation)
ENTITLEMENTS := SeratoDynamicAnalyzer/Resources/SeratoDynamicAnalyzer.entitlements

.PHONY: release deps bundle-python bundle-swift sign dmg clean distclean

# ──────────────────────────────────────────────────────────────────────────────
# release: One-command pipeline (D-10)
# ──────────────────────────────────────────────────────────────────────────────
release: deps bundle-python bundle-swift sign dmg

# ──────────────────────────────────────────────────────────────────────────────
# deps: Install build tools — idempotent
# ──────────────────────────────────────────────────────────────────────────────
deps:
	which uv || brew install uv
	@echo "deps OK — uv present"

# ──────────────────────────────────────────────────────────────────────────────
# BeeWare tarball download (file rule — runs only once, cached in build/cache/)
# ──────────────────────────────────────────────────────────────────────────────
$(BEEWARE_TAR):
	mkdir -p build/cache
	curl -L "$(BEEWARE_URL)" -o "$(BEEWARE_TAR)"

# ──────────────────────────────────────────────────────────────────────────────
# Extract Python.framework from BeeWare tarball (file rule — cached)
# Layout after extraction: build/python-runtime/Python.framework/Versions/3.12/bin/python3
# This matches the path used in PythonBridge.pythonBinaryURL().
# ──────────────────────────────────────────────────────────────────────────────
build/python-runtime/Python.framework: $(BEEWARE_TAR)
	mkdir -p build/python-runtime
	tar -xzf "$(BEEWARE_TAR)" -C build/python-runtime
	@echo "BeeWare layout:"
	@ls build/python-runtime/
	@echo "Python binary check:"
	@ls build/python-runtime/Python.framework/Versions/3.12/bin/python3 2>/dev/null \
	    && echo "python3 found at expected path" \
	    || (echo "WARNING: python3 not at expected path — check build/python-runtime/ layout and update PythonBridge.swift"; ls -R build/python-runtime/ | head -40)

# ──────────────────────────────────────────────────────────────────────────────
# Create relocatable venv and install Python dependencies (file rule — cached)
# ──────────────────────────────────────────────────────────────────────────────
build/python-runtime/venv: build/python-runtime/Python.framework
	uv venv --relocatable \
	    --python build/python-runtime/Python.framework/Versions/3.12/bin/python3 \
	    build/python-runtime/venv \
	|| ( \
	    echo "uv --relocatable failed; falling back to venv --copies"; \
	    build/python-runtime/Python.framework/Versions/3.12/bin/python3 \
	        -m venv --copies build/python-runtime/venv \
	)
	uv pip install -r python/requirements.txt \
	    --python build/python-runtime/venv/bin/python3

# ──────────────────────────────────────────────────────────────────────────────
# bundle-python: Copy Python.framework + venv site-packages + analyze.py into .app
# ──────────────────────────────────────────────────────────────────────────────
bundle-python: build/python-runtime/Python.framework build/python-runtime/venv
	rm -rf "$(PYTHON_RUNTIME)"
	mkdir -p "$(PYTHON_RUNTIME)"
	# Copy BeeWare Python.framework (already relocatable — no install_name_tool needed)
	cp -R build/python-runtime/Python.framework "$(PYTHON_RUNTIME)/"
	# Merge venv site-packages into the framework's site-packages
	cp -R build/python-runtime/venv/lib/python3.12/site-packages/. \
	      "$(PYTHON_RUNTIME)/Python.framework/Versions/3.12/lib/python3.12/site-packages/"
	# Copy analyze.py to scripts/
	mkdir -p "$(SCRIPTS_DIR)"
	cp python/analyze.py "$(SCRIPTS_DIR)/"
	# Ensure python3 binary is executable
	chmod +x "$(PYTHON_RUNTIME)/Python.framework/Versions/3.12/bin/python3"
	@echo "bundle-python: Python runtime embedded"

# ──────────────────────────────────────────────────────────────────────────────
# bundle-swift: Build Swift app via xcodebuild, copy .app into build/
# Requires Xcode.app at /Applications/Xcode.app (D-02-03 confirmed)
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
	cp -R build/derived/Build/Products/Release/$(APP_NAME).app "$(APP)"
	@echo "bundle-swift: .app copied to $(APP)"

# ──────────────────────────────────────────────────────────────────────────────
# sign: Bottom-up ad-hoc code signing (D-12, D-13, CLAUDE.md signing order)
# Order: 1) all .so/.dylib  2) Python.framework  3) outer .app
# No --timestamp flag needed for ad-hoc signing (timestamps are for Developer ID only)
# ──────────────────────────────────────────────────────────────────────────────
sign:
	# 1. Sign all .so and .dylib files inside python-runtime (bottom layer first)
	find "$(PYTHON_RUNTIME)" \( -name "*.dylib" -o -name "*.so" \) \
	    | xargs -I{} codesign --force --sign - --options runtime "{}"
	# 2. Sign Python.framework as a unit
	codesign --force --sign - --options runtime \
	    "$(PYTHON_RUNTIME)/Python.framework"
	# 3. Sign the outer .app with entitlements (D-13: allow-unsigned-executable-memory + disable-library-validation)
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
# clean: Remove build artifacts (keeps BeeWare cache + python-runtime venv)
# ──────────────────────────────────────────────────────────────────────────────
clean:
	rm -rf "build/$(APP_NAME).app" build/derived "build/$(APP_NAME).dmg" build/xcodebuild.log
	@echo "clean: build artifacts removed (BeeWare cache preserved)"

# ──────────────────────────────────────────────────────────────────────────────
# distclean: Full clean including BeeWare cache and venv
# ──────────────────────────────────────────────────────────────────────────────
distclean:
	rm -rf build/
	@echo "distclean: all build artifacts and cache removed"
