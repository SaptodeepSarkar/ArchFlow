# ADR-002 — Native platform shells over a shared domain core

Date: 2026-09-16

## Problem

Vaani must share semantics across Android, Linux, and Windows while respecting Android IME constraints and OS-specific global input/insertion behavior.

## Options considered

1. One cross-platform UI/runtime for every surface.
2. Shared Rust domain/core contracts with native Android Kotlin and native desktop adapters.
3. Arbitrary dynamic plugins that load platform code at runtime.

## Evidence

The current repository already has a Rust Linux controller/core and a native Kotlin `InputMethodService`. Android’s IME is lifecycle- and platform-owned, while Windows input injection is subject to integrity/UIPI restrictions documented by Microsoft. Wispr Flow’s current product also separates desktop control surfaces from mobile keyboard surfaces. [Android InputMethodService](https://developer.android.com/reference/android/inputmethodservice/InputMethodService), [Microsoft SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput), [Wispr Flow features](https://try.wisprflow.ai/)

## Decision

Use shared, serializable domain contracts and portable deterministic logic. Keep Android IME/UI, Linux shell/insertion, and Windows shell/insertion native to each platform. Plugins register trusted implementations through explicit interfaces and manifests; no arbitrary code loader is part of the product contract.

## Tradeoffs

Some UI and OS integration code is duplicated, but lifecycle correctness, accessibility, and insertion safety are better than forcing one UI abstraction across incompatible surfaces.

## Reversal cost

Moderate: domain contracts remain reusable if a future shared UI is justified; platform shells would need replacement, not the data/model pipeline.
