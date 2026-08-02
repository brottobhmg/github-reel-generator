# Contributing

Thanks for your interest in contributing to the GitHub Reel Generator! 🎉

Please take a moment to read these guidelines before opening an issue or a pull
request.

---

## Code of conduct

Be respectful and constructive. Harassment or discrimination of any kind will
not be tolerated.

---

## How to contribute

### 1. Reporting bugs

Open an issue and include:

- A clear, descriptive title.
- Steps to reproduce the bug.
- Expected vs. actual behavior.
- Relevant logs (from `logs/`) and environment details (OS, Python version).

### 2. Suggesting features

Open an issue describing:

- The problem you are trying to solve.
- A proposed solution or approach.
- Any alternatives you considered.

### 3. Submitting code

1. **Fork** the repository and create a branch from `master`:

   ```bash
   git checkout -b feat/my-feature
   ```

2. **Make your changes**, following the guidelines below.

3. **Run the tests**:

   ```bash
   pytest
   ```

4. **Commit** with a clear, conventional message (see below).

5. **Push** and open a pull request describing your changes.

---

## Development setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps
cp .env.example .env   # add your keys
```

---

## Guidelines

### Code style

- Follow [PEP 8](https://peps.python.org/pep-0008/).
- Use **type hints** on all public functions.
- Add **docstrings** (Google style) to public functions and classes.
- Keep functions small and focused on a single responsibility.

### Logging

- Use the `logging` module via `get_logger(__name__)` from `logging_config.py`.
- **Do not use `print()`** for application logging.

### Configuration

- Never hardcode secrets or infrastructure URLs.
- Add any new configuration to `config.py` and document it in `.env.example`.

### Testing

- Add tests for new logic in the `tests/` directory.
- Ensure the full suite passes before submitting.

### Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add support for Instagram uploads
fix: correct subtitle timing on short videos
refactor: extract video assembly into its own module
docs: update architecture diagram
test: add tests for the job processor
chore: update dependencies
```

---

## Security

- **Never commit API keys, tokens, or secrets.**
- Keep secrets in `.env` (gitignored).
- Do not hardcode private endpoints or infrastructure URLs.
- If you discover a security issue, please report it privately rather than
  opening a public issue.
