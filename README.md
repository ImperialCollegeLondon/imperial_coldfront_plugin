# Imperial College London Coldfront Plugin

Plugin for the Coldfront HPC management platform that provides customisations for
Imperial College London.

As this repository is a plugin it must be used in conjunction with a Coldfront
instance. Limited development is possible working with this repository in isolation via
Unit Tests and QA tooling. For interactive testing in the browser, a dedicated
development environment is provided by [GitHub:
ImperialCollegeLondon/coldfront_development_environment] that contains a Coldfront
environment with the necessary configuration.

This repository is a reusable Django app and so follows the associated conventions. See
[Django Advanced Tutorial: How to write reusable apps] for further information.

[GitHub: ImperialCollegeLondon/coldfront_development_environment]: https://github.com/ImperialCollegeLondon/coldfront_development_environment
[Django Advanced Tutorial: How to write reusable apps]: https://docs.djangoproject.com/en/5.1/intro/reusable-apps/

## Dependency Management

This is a Python application that uses [`pip-tools`] for packaging and dependency management. It also provides [`pre-commit`](https://pre-commit.com/) hooks (for for [ruff](https://pypi.org/project/ruff/) and [`mypy`](https://mypy.readthedocs.io/en/stable/)) and automated tests using [`pytest`](https://pytest.org/) and [GitHub Actions](https://github.com/features/actions). Pre-commit hooks are automatically kept updated with a dedicated GitHub Action, this can be removed and replace with [pre-commit.ci](https://pre-commit.ci) if using an public repo. It was developed by the [Imperial College Research Computing Service](https://www.imperial.ac.uk/admin-services/ict/self-service/research-support/rcs/).

[`pip-tools`] is chosen as a lightweight dependency manager that adheres to the [latest standards](https://peps.python.org/pep-0621/) using `pyproject.toml`.

### Updating Dependencies

To add or remove dependencies:

1. Edit the `dependencies` variables in the `pyproject.toml` file (aim to keep development tools separate from the project requirements).
2. Update the requirements files:
   - `pip-compile` for `requirements.txt` - the project requirements.
   - `pip-compile --extra dev -o dev-requirements.txt` for the development requirements.
   - `pip-compile --extra doc -o doc-requirements.txt` for the documentation tools.
3. Sync the files with your installation (install packages):
   - `pip-sync *requirements.txt`

To upgrade pinned versions, use the `--upgrade` flag with `pip-compile`.

Versions can be restricted from updating within the `pyproject.toml` using standard python package version specifiers, i.e. `"black<23"` or `"pip-tools!=6.12.2"`

## Usage

To get started:

1. Create and activate a [virtual environment](https://docs.python.org/3/library/venv.html):

   ```bash
   python -m venv .venv
   source .venv/bin/activate # with Powershell on Windows: `.venv\Scripts\Activate.ps1`
   ```

1. Install development requirements:

   ```bash
   pip install -r dev-requirements.txt
   ```

1. Install the git hooks:

   ```bash
   pre-commit install
   ```
