# uvtool — A Fictional Local Python Build Tool

uvtool is a hypothetical command-line tool designed to simplify Python
project bootstrapping. This manual describes its (entirely fictional)
behaviour for demonstration purposes only.

## Installation

Install uvtool via `pip install uvtool`. The tool requires Python 3.10
or newer. There is no remote registry; uvtool operates entirely on the
local filesystem.

## Bootstrapping a Project

Run `uvtool init my-project` to create a new project scaffold. The
scaffold includes a `pyproject.toml`, a `src/` directory, a basic test
directory, and a `.gitignore` appropriate for Python projects.

## Dependency Management

uvtool uses a `uvtool.lock` file to pin transitive dependencies. Add a
dependency with `uvtool add requests`. The lock file is updated in place
and the dependency is installed into the active virtual environment.

## Running Tests

Run `uvtool test` to execute the test suite. The tool discovers tests
under `tests/` and runs them with pytest. Coverage is reported to
`coverage.xml` and a summary is printed to the console.

## Removing a Project

Run `uvtool remove my-project` to delete the project directory. The
command refuses to remove directories that contain a `.git` folder
unless `--force` is passed.
