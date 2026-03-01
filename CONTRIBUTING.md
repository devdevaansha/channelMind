# Contributing to ChannelMind

Thanks for contributing. This guide keeps changes consistent and reviewable.

## Development Setup

1. Fork the repository and clone your fork.
2. Create a feature branch from `main`.
3. Copy environment template and configure values:

```bash
cp .env.example .env
```

4. Add your Google service account key:

```bash
cp /path/to/sa.json secrets/sa.json
```

5. Start the stack:

- GPU path:

```bash
docker compose up --build
```

- CPU path:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up --build
```

## Running Tests

```bash
pip install -r requirements/test.txt
pytest
```

If your change affects pipeline behavior, include at least one test for success path and one for failure or retry behavior.

## Pull Request Guidelines

- Keep PRs focused and small enough to review.
- Write clear commit messages.
- Update docs when behavior/configuration changes.
- Follow `CODE_OF_CONDUCT.md`.
- Include testing notes in the PR description:
  - What you ran
  - What changed
  - Any known limitations

## Reporting Issues

Open an issue with:

- Problem summary
- Reproduction steps
- Expected behavior
- Actual behavior
- Relevant logs/screenshots
- Environment details (OS, Docker version, GPU/CPU mode)

## Security and Support

- For vulnerabilities, follow `SECURITY.md` (do not post publicly).
- For general help, see `SUPPORT.md`.
