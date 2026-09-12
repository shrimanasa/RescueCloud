# Contributing to RescueCloud

Thank you for your interest in contributing to RescueCloud.

## Getting Started

1. Fork the repository and clone your fork.
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your changes following the guidelines below.
4. Run the full test suite: `pytest --tb=short -q`
5. Push your branch and open a Pull Request.

## Code Style

- **Python**: follow PEP 8; use type hints for all function signatures.
- **Docstrings**: use Google-style docstrings for all public functions.
- **Constants**: define module-level constants in SCREAMING_SNAKE_CASE.
- **Imports**: group as stdlib → third-party → local, separated by blank lines.

## Commit Messages

Use Conventional Commits format:
```
feat(component): short description
fix(component): short description
docs(component): short description
refactor(component): short description
test(component): short description
```

## PHI and Secrets Policy

- Never commit real patient data, even anonymised.
- Never commit credentials, API keys, or JWT secrets.
- `wal_archive/`, `backups/`, `data/synthea/` are gitignored — keep it that way.
- If you accidentally commit a secret, rotate it immediately and purge git history.

## Reporting Security Issues

Do not open a public GitHub issue for security vulnerabilities.
Email the maintainer directly with a proof-of-concept.
Allow 90 days for remediation before public disclosure.


## Documentation Standards

- All Python modules must have a module-level docstring explaining purpose and usage.
- All public functions must have docstrings with Args/Returns/Raises sections.
- Architecture decisions must be documented in docs/ARCHITECTURE.md.
- API changes must be reflected in docs/API_REFERENCE.md.
- Empirical claims in README.md must cite their source (CSV column and computation).


## Release Process

1. Update `API_VERSION` in `backend/main.py`
2. Update the Changelog section in `README.md`
3. Run full test suite: `pytest --tb=short -q`
4. Tag the release: `git tag -a v2.5.0 -m 'Release v2.5.0'`
5. Push tag: `git push origin v2.5.0`
6. CI will build and push the Docker image to the registry
7. Update `k8s/*/deployment.yaml` image tag and apply to the cluster


## Dependency Management

- Pin all Python dependencies to specific versions in `requirements.txt`.
- Run `pip audit` before merging to check for known vulnerabilities.
- For Node.js (blockchain), `package-lock.json` is committed — never delete it.
- Use `pip-compile` (pip-tools) to generate `requirements.txt` from `requirements.in`.
- Do not add new dependencies without justification in the PR description.


## Environment Parity

Always develop against an environment that matches production as closely as possible:

- Use Docker Compose (not bare Python) for local development
- Use the same PostgreSQL major version (16) as production
- Use the same Redis major version (7) as production
- Test with the same Isolation Forest model that runs in production
- Never use `APP_ENV=development` shortcuts that bypass security checks


## Backwards Compatibility

- API response schema changes must be backwards compatible (add fields, never remove).
- Event schema changes must be backwards compatible (use Optional fields for new data).
- Database schema changes must use `ALTER TABLE ADD COLUMN IF NOT EXISTS`.
- Joblib model files are not backwards compatible across scikit-learn major versions.
- K8s manifest changes must be tested in a staging cluster before merging.


## Getting Help

- **Questions about the codebase**: Open a GitHub Discussion
- **Bug reports**: Use the bug report issue template
- **Feature requests**: Use the feature request issue template
- **Security vulnerabilities**: Email the maintainer directly (see SECURITY.md)
- **HIPAA compliance questions**: Consult your hospital's compliance officer;
  RescueCloud documentation is not a substitute for legal compliance advice
