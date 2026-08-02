# syseng-tools

Systems-engineering tooling for rocket program documentation: StrictDoc
integration, controlled-record checks, risk reporting, and generated review
artifacts.

## Documentation Boundary

Author-facing usage is defined in `docs/strictdoc-integration.md` in
[Georgia-Tech-GNC/docs-systems-engineering](https://github.com/Georgia-Tech-GNC/docs-systems-engineering).

This README is for maintaining the tooling package. It explains what the package
owns and how the commands work under the hood.

## Author Installation

Program repositories should pin `syseng-tools` in `requirements-tools.txt`:

```text
syseng-tools @ git+https://github.com/Georgia-Tech-GNC/syseng-tools.git@v0.1.1
```

Authors install the pinned tools from the program repository:

```text
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-tools.txt
syseng --help
```

The virtual environment is local developer state and should not be committed (add `.venv/` to the `.gitignore`).

## Command Entry Point

```text
syseng check
syseng export
syseng serve
syseng risk
```

The installed console command is `syseng`.

Program repositories provide a `syseng.toml` file. The command reads that file
to locate the project root, project prefix, records directory, and allowed
applicability values.

## Command Internals

`syseng check` invokes StrictDoc parsing first, then runs package Python checks
against the generated StrictDoc JSON model.

`syseng export` copies the package grammar to `build/syseng/grammar/`, writes a
temporary StrictDoc config to `build/syseng/strictdoc_config.py`, invokes
StrictDoc export for HTML, JSON, and Excel, then generates custom reports.

`syseng serve` validates that `build/strictdoc/html/index.html` exists, then
serves `build/strictdoc/html` with Python's static HTTP server. It does not run
`syseng export` implicitly.

`syseng risk` regenerates the risk register from an existing StrictDoc
JSON export. By default, it reads `build/strictdoc/json/index.json` and writes
`risk-register.json`, `risk-register.csv`, and `risk-register.md` to
`build/syseng/`.

## Program Contract

Program repositories are expected to provide:

- `syseng.toml`
- a configured records directory
- StrictDoc `.sdoc` source files using the package grammar

The `syseng.toml` schema is defined in `docs/strictdoc-integration.md` in
[Georgia-Tech-GNC/docs-systems-engineering](https://github.com/Georgia-Tech-GNC/docs-systems-engineering).

During local development, install this package in editable mode:

```text
python -m pip install -e .
```

Run the test suite with:

```text
python -m unittest discover -s tests
```

Tests that exercise `syseng serve` bind a local `127.0.0.1` socket.
