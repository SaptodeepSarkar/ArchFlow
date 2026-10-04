.DEFAULT_GOAL := help

.PHONY: help desktop-debug desktop-release android-debug android-release install-desktop test-desktop test-android data-check train-stt train-formatter

help:
	@printf '%s\n' \
	  'Vaani targets:' \
	  '  make desktop-debug     Build the Linux GTK4 desktop application' \
	  '  make desktop-release   Build release binaries for install/package' \
	  '  make android-debug     Build app-debug.apk' \
	  '  make android-release   Build an unsigned release APK' \
	  '  make install-desktop   Install the built Linux GTK4 application locally' \
	  '  make test-desktop      Run the Rust workspace tests' \
	  '  make test-android      Run Android JVM unit tests' \
	  '  make data-check        Validate the shared formatter dataset when present' \
	  '  make train-stt ARGS="..."       Run the shared STT pipeline' \
	  '  make train-formatter ARGS="..." Run the shared formatter pipeline'

desktop-debug:
	cargo build --workspace
	cargo build -p vaani-local --features native-ui

desktop-release:
	cargo build --workspace --release
	cargo build --release -p vaani-local --features native-ui

android-debug:
	cd android && ./gradlew assembleDebug

android-release:
	cd android && ./gradlew assembleRelease

install-desktop: desktop-release
	./install.sh

test-desktop:
	cargo test --workspace

test-android:
	cd android && ./gradlew testDebugUnitTest

data-check:
	./pipelines/validate-shared-data.sh

train-stt:
	./pipelines/stt/train.sh $(ARGS)

train-formatter:
	./pipelines/llm/train-formatter.sh $(ARGS)
