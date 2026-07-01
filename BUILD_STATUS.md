# UGAF Build Status

**Generated:** 2026-07-01, verified by running each tool directly against the working tree (Python 3.14.6, Windows).

## Summary

| Check | Status | Detail |
|---|---|---|
| Package build/import | ✅ PASS | `ugaf` installed (editable, egg-info present), all subpackages import cleanly |
| Test suite (`pytest`) | ✅ PASS | 415 / 415 passed, 2.3–3.2s |
| Lint (`ruff check .`) | ✅ PASS | 0 errors, 0 warnings ("All checks passed!") |
| Format (`ruff format --check .`) | ✅ PASS | 97 files, all already formatted |
| Type check (`mypy ugaf`, strict) | ✅ PASS | "Success: no issues found in 58 source files" |
| Coverage | ⚠️ 79% overall | Misleading in aggregate — see gap breakdown below |
| CI/CD | ❌ ABSENT | No `.github/workflows/`, `.gitlab-ci.yml`, `.circleci/`, or any other CI config found anywhere in the repo |

## Test Suite Detail

```
415 passed in 2.30s–3.16s (varies by run / coverage instrumentation)
```

No skipped tests, no xfails, no warnings emitted. Tests span: config, event bus, bootstrap, logger, input (adb/manager/provider/registry/types/windows/exceptions), imaging (backend/exceptions/image/manager/opencv_backend/types), plugins (lifecycle/loader/manager/registry/validator), sdk (game/types), vision (color/detector/exceptions/manager/matcher/ocr/pixel/provider/region/screenshot). 34 test files total.

**Caveat on what "passing" proves:** confirmed by the subsystem audits, a large fraction of imaging/vision tests mock the backend layer (`MagicMock(spec=ImageBackend)`) or, in the OpenCV backend test's case, patch `sys.modules["cv2"]` entirely — meaning `cv2.matchTemplate`, `cv2.Canny`, `cv2.SimpleBlobDetector` etc. are never actually invoked by the test suite even though they're invoked in production code. Passing tests here verify call-forwarding and control flow, not real image-processing correctness. Similarly, ADB tests mock `subprocess.run` and verify constructed argv, not actual device interaction.

## Coverage Gap Breakdown (why 79% overshoots real confidence)

| File | Line coverage | What's actually untested |
|---|---|---|
| `ugaf/core/cli.py` | **0%** | Entire CLI — no test file exists for it at all |
| `ugaf/core/plugin.py` | **0%** | Dead code (unreachable, nothing imports it) |
| `ugaf/imaging/filters.py`, `formats.py`, `operations.py` | **0%** | Not real gaps — these are pure `X = str` alias declarations with zero logic, dead weight either way |
| `ugaf/core/di.py` | **35%** | The entire auto-wiring, circular-dependency-detection, and singleton-caching engine (lines 246–309) — the most architecturally important logic in `core/` — is unexercised. No `test_di.py` exists. |
| `ugaf/core/plugin_loader.py` | **40%** | Legacy loader's discovery/import error paths |
| `ugaf/core/platform.py` | **61%** | No `test_platform.py` exists; `detect_platform()` itself and all `is_windows`/`is_linux`/`is_macos` properties are untested |
| `ugaf/core/health.py` | **64%** | No `test_health.py` exists; `run_all`/`run_one`'s exception-isolation behavior is unverified |
| `ugaf/core/bootstrap.py` | **63%** | Signal-handling and some error branches untested |
| `ugaf/vision/provider.py` | **82%** | Also has a cosmetic duplicated `@abstractmethod` decorator on `pixel_matches` (harmless, but a review-quality smell) |
| `ugaf/vision/detector.py` | **70%** | Blob/line-detection branches partially untested |
| `ugaf/vision/matcher.py` | **86%** | NMS edge cases |
| `ugaf/imaging/opencv_backend.py` | **89%** | A few draw/encode branches |

Everything else (config, event_bus, logger, context, exceptions, imaging/image.py, imaging/manager.py, input/registry.py, input/provider.py, plugins/registry.py, plugins/validator.py, sdk/*) sits at 90–100% and is genuinely well tested per the subsystem audits.

## Static Analysis Detail

- **ruff**: configured with `select = ["E", "F", "I", "N", "W", "D", "UP"]` (pycodestyle, pyflakes, isort, pep8-naming, warnings, pydocstyle, pyupgrade) — a reasonably strict rule set, and it's fully clean.
- **mypy**: `strict = true` in `pyproject.toml`, plus `warn_unused_configs`, `warn_redundant_casts`, `warn_unused_ignores`. Passing strict mypy across 58 files with 0 issues is a genuinely strong signal — this is not a superficial check.
- **black**: configured in `pyproject.toml` but `ruff format` is the one actually verified here (equivalent formatting engine); no conflicts detected.

## Environment / Dependency Notes

- `cv2` (opencv-python) 4.13.0 and `numpy` 2.3.5 are installed in this environment, so imaging/vision imports succeed.
- `pytesseract` is **not installed**, consistent with `ugaf/vision/ocr.py` never importing it — OCR has no backend to bind to even if the stub were filled in.
- `pyautogui`/`keyboard`/`mouse` (the `[input]` optional dependency group) were not explicitly re-verified in this session beyond the windows.py audit, which confirmed `windows.py` lazily checks for their presence and raises `ConnectionFailedError` if absent rather than crashing at import time.
- No `requirements.txt`/lockfile beyond `pyproject.toml`'s dependency groups — dependency pinning is loose (`>=` bounds only), which is normal for alpha but worth tightening before a real release.

## Suggested Fixes, Ranked by Leverage

1. **Add `.github/workflows/ci.yml`** running `pytest`, `ruff check`, `ruff format --check`, and `mypy` on every PR — currently nothing enforces any of the green results above; they could regress silently.
2. **Write `tests/test_di.py`** covering: double-registration errors, transient vs singleton instance identity, `resolve_all`, circular-dependency raising, and auto-wiring with missing/unregistered dependencies. This is the highest-value missing test file in the repo given how much of `core/`'s object graph depends on `di.py` working correctly.
3. **Write `tests/test_health.py` and `tests/test_platform.py`** — currently zero direct coverage.
4. **Write `tests/test_cli.py`** — the CLI is the actual user-facing entry point and has no tests at all.
5. **Fix the `health.py` docstring/implementation mismatch** — either make `run_all` genuinely concurrent (`asyncio.gather`) or correct the docstring claiming it already is.
6. **Fix `vision/provider.py`'s duplicated `@abstractmethod`** on `pixel_matches` — trivial one-line cleanup.
