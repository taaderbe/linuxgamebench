# Changelog

All notable changes to Linux Game Bench will be documented here.

## 2026-01-23

### Added
- Screenshot upload for benchmarks (Free: 1, Premium: 5 per benchmark)
- Lightbox with keyboard navigation for screenshots
- Like count badge on My Benchmarks cards
- FAQ entry for driver version detection (install mesa-utils or nvidia-utils)

### Fixed
- Like button now disabled for own benchmarks
- iOS touch/hover issues on buttons
- Summary row now updates FPS values when Main Filter is applied (no need to expand first)
- Driver version detection fallback via vulkaninfo for AMD/Mesa GPUs
- Consistent terminology: "None" instead of "Off" for game settings (RT, Frame Gen, AA)

## 2026-01-22

### Added
- Like/Unlike benchmarks feature (premium)
- Report benchmark feature
- Premium tiers (Bronze, Silver, Gold) with badges and stars
- Liked benchmarks filter in My Benchmarks

### Fixed
- Frame Distribution hidden when compare is active
- Compare filter excludes currently selected Main run

## 2026-01-21

### Added
- Hardware comparison view on homepage
- Frame Distribution chart in comparison view

## 2026-01-17

### Fixed
- Layout shift when pagination changes
- Multi-GPU sensor metrics display

### Added
- Page size selector (5/10/25/50 benchmarks per page)

## 2026-01-07

### Changed
- Documentation restructure

### Fixed
- BASE_URL default configuration

## 2026-01-06

### Added
- Email authentication (register, verify, login, password reset)
- Two-factor authentication (2FA/TOTP)
- JWT tokens with 30-day expiry
- CLI login with 2FA support

## 2026-01-05

### Added
- openSUSE Tumbleweed support

## 2026-01-01

### Added
- Initial release
- Steam game detection and benchmarking
- MangoHud integration for frametime recording
- HTML reports with interactive charts
- Upload to community database
- Multi-GPU support
- Game settings tracking (preset, RT, upscaling, etc.)
