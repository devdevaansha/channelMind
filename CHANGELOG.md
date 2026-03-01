# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Open-source documentation rewrite in `README.md` with GPU/CPU setup paths.
- CPU fallback stack via `docker-compose.cpu.yml`.
- CPU worker image via `Dockerfile.worker.cpu`.
- `CONTRIBUTING.md` contributor workflow guide.
- `LICENSE` with GNU GPL v3 terms.
- Repository community standards files (`CODE_OF_CONDUCT.md`, `SECURITY.md`, issue templates, PR template).

### Changed

- Project naming/docs updated to **ChannelMind**.
- Default local DB and Pinecone index naming switched from `atva` to `channelmind`.
- `.env.example` expanded with `TORCH_CUDA_TAG` and active `WHISPER_DEVICE`.
- `.gitignore` updated to exclude local debug/test artifacts.
