# Imperial College London Coldfront Plugin

Plugin for the Coldfront HPC management platform that provides customisations for
Imperial College London.

This is a Python application that uses [`pip-tools`] for packaging and dependency management. It also provides [`pre-commit`](https://pre-commit.com/) hooks (for for [ruff](https://pypi.org/project/ruff/) and [`mypy`](https://mypy.readthedocs.io/en/stable/)) and automated tests using [`pytest`](https://pytest.org/) and [GitHub Actions](https://github.com/features/actions). Pre-commit hooks are automatically kept updated with a dedicated GitHub Action, this can be removed and replace with [pre-commit.ci](https://pre-commit.ci) if using an public repo. It was developed by the [Imperial College Research Computing Service](https://www.imperial.ac.uk/admin-services/ict/self-service/research-support/rcs/).

[`pip-tools`] is chosen as a lightweight dependency manager that adheres to the [latest standards](https://peps.python.org/pep-0621/) using `pyproject.toml`.

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

1. (Optionally) install tools for building documentation:

   ```bash
   pip install -r doc-requirements.txt
   ```

1. Install the git hooks:

   ```bash
   pre-commit install
   ```

1. Run the main app:

   ```bash
   python -m imperial_coldfront_plugin
   ```

1. Run the tests:

   ```bash
   pytest
   ```

## Updating Dependencies

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

## Making Migrations

As a standalone Django application this plugin provides models to extend the
Coldfront data model. A helper script is provided to generate migrations for
these models. To use it, run the following command:

```bash
python makemigrations.py
```

This is equivalent to running `python manage.py makemigrations` in a Django
project and all the same options are available. See options with:

```bash
python makemigrations.py --help
```

## Customising

All configuration can be customised to your preferences. The key places to make changes
for this are:

- The `pyproject.toml` file, where you can edit:
  - The build system (change from setuptools to other packaging tools like [Hatch](https://hatch.pypa.io/) or [flit](https://flit.pypa.io/)).
  - The python version.
  - The project dependencies. Extra optional dependencies can be added by adding another list under `[project.optional-dependencies]` (i.e. `doc = ["mkdocs"]`).
  - The `mypy` and `pytest` configurations.
- The `.pre-commit-config.yaml` for pre-commit settings.
- The `.github` directory for all the CI configuration.

[`pip-tools`]: https://pip-tools.readthedocs.io/en/latest/

## Publishing

The GitHub workflow includes an action to publish on release.
To run this action, uncomment the commented portion of `publish.yml`, and modify the steps for the desired behaviour (publishing a Docker image, publishing to PyPI, deploying documentation etc.)
