# compose-doctor

A static linter for `docker compose` files. It reads the YAML and tells you about
the handful of things that are fine in a demo and painful at 2 a.m.: a published
port on `0.0.0.0`, two services fighting over the same host port, a named volume
nobody mounts, `json-file` logging with no size limit, a service that carries no
`restart` policy, an environment entry that silently resolves to an empty string.

No Docker socket, no container start, no network. That means it is safe to run in
CI, on a machine where you do not have the docker group, or against a compose
file you are reviewing but not deploying.

## Why another linter

`docker compose config` validates the schema, which is genuinely useful and
catches real problems. It does not have an opinion about a `latest` tag, a bind
mount whose source vanished when you moved the directory, or log files that grow
until the disk fills. Those are the failures I keep seeing on self-hosted boxes,
and most of them are visible from the file alone.

## Usage

```bash
pip install pyyaml          # the only dependency
python3 compose_doctor.py docker-compose.yml
python3 compose_doctor.py - --json < compose.yaml   # (single file, JSON output)
python3 compose_doctor.py stacks/*/compose.yaml --check-paths
```

```
warn  W102  compose.yaml:services.web           image 'nginx' is unpinned or latest
info  I201  compose.yaml:services.web           port 8080 binds on all interfaces
warn  W104  compose.yaml:services.web           publishes ports but has no healthcheck
warn  W105  compose.yaml:services.web           log driver 'json-file' without max-size
error E003  compose.yaml:services.db            host port 8080 already published by web
warn  W106  compose.yaml:services.db            'POSTGRES_PASSWORD' : no default, fails silently if unset
warn  W101  compose.yaml:volumes.pgdata         declared but not used by any service
```

Exit codes: `0` no errors, `1` at least one `E` finding, `2` the file did not parse.

`--check-paths` additionally verifies that bind-mount sources exist on the host
running the check. Leave it off when linting on a different machine than the one
that deploys.

## Rules

| Code | Severity | What it means |
|------|----------|---------------|
| E001 | error | service has neither `image` nor `build` |
| E002 | error | bind-mount source missing (`--check-paths` only) |
| E003 | error | two services publish the same host port |
| W101 | warn  | named volume declared and never mounted |
| W102 | warn  | image uses `latest` or no tag |
| W103 | warn  | no `restart` policy |
| W104 | warn  | publishes ports, has no healthcheck |
| W105 | warn  | `json-file`/`local` logs with no `max-size` |
| W106 | warn  | environment entry with no default value |
| I201 | info  | port bound on all interfaces |

## Tests

```bash
python3 -m unittest -v test_compose_doctor
```

Standard library `unittest`, no pytest needed. The tests build compose documents
in memory, so they do not touch the filesystem or a daemon.

## What it deliberately does not do

- It does not resolve `extends`, `include` or environment-file interpolation.
  If your setup relies on those, lint the resolved output (`docker compose config`)
  instead.
- It does not talk to the registry or pull images.
- It has no plugin system. When I want a new rule I add a function to `check()`
  and a test next to it.

## License

MIT. See [LICENSE](LICENSE).
