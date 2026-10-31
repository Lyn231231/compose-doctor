<div align="center">

# compose-doctor

**Static analysis for docker-compose files — catch the mistakes before `docker compose up` does.**

[![tests](https://img.shields.io/badge/tests-passing-brightgreen?style=flat-square)](#quick-start)
[![python](https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square&logo=python&logoColor=white)](#quick-start)
[![deps](https://img.shields.io/badge/dependencies-none-lightgrey?style=flat-square)](#quick-start)
[![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

</div>

## About

A single-file checker that parses the YAML tree instead of shelling out to
`docker compose config`. It knows the failure modes that only show up at runtime:
services that `depends_on` something that does not exist, host ports bound twice,
volumes declared but never mounted, images without a tag (silently drifting to
`:latest`), and healthchecks that reference a binary the image does not have.

Nothing is executed; the file is never sent anywhere. Exit codes are stable
(`0` clean, `1` findings, `2` unparsable input) so it drops straight into CI.

## Quick start

```bash
git clone https://github.com/Lyn231231/compose-doctor
cd compose-doctor
python3 compose_doctor.py example/compose.yaml
python3 -m unittest -v      # full suite, no third-party dependencies
```

## Configuration

| Key | Description |
| --- | --- |
| `--strict` | treat warnings as errors (exit 1) |
| `--json` | machine-readable output for CI |
| `--ignore RULE_ID` | skip a specific rule, repeatable |
## Roadmap

- [ ] Rule for `network_mode: service:` cycles
- [ ] SARIF output for GitHub code scanning
- [ ] Pre-commit hook packaging

## Contributing

Issues and pull requests are welcome. Please keep changes small and focused,
and add a test for any behaviour change — every repository here ships with a
runnable test suite and no third-party dependencies, so CI is just
`python3 -m unittest` / `bash test_*.sh`.

## License

[MIT](LICENSE)
