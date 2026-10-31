#!/usr/bin/env python3
"""compose-doctor — read a compose file and report the things that bite later.

Static checks only: no Docker daemon is contacted, so this is safe to run in CI
or on a box where you do not have (or do not want to use) the docker socket.

Checks
------
  E001  service with neither ``image`` nor ``build``
  E002  bind mount source does not exist on this host (only if --check-paths)
  E003  duplicate published host ports
  W101  named volume declared but not used by any service
  W102  service uses the ``latest`` tag (or no tag at all)
  W103  no ``restart`` policy
  W104  healthcheck missing on a service exposing ports
  W105  container started without a log size limit (unbounded json-file)
  W106  environment variable referenced with no default and not set here
  I201  service publishes on 0.0.0.0 (reachable from outside the host)

Exit code: 0 if no errors (warnings allowed), 1 if any error, 2 on parse failure.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - environment dependent
    yaml = None

SEVERITY = {"E": "error", "W": "warn", "I": "info"}
UNBOUNDED_LOG_DRIVER = {"json-file", "local"}


class Finding:
    __slots__ = ("code", "where", "message")

    def __init__(self, code: str, where: str, message: str):
        self.code, self.where, self.message = code, where, message

    def __str__(self) -> str:
        return f"{SEVERITY[self.code[0]]:<5} {self.code}  {self.where:<28} {self.message}"


def parse_ports(entry) -> tuple[str, str] | None:
    """Return (host_ip, host_port) for short-syntax port entries."""
    if isinstance(entry, dict):
        # long syntax
        published = entry.get("published")
        if published is None:
            return None
        return str(entry.get("host_ip", "0.0.0.0")), str(published)
    if not isinstance(entry, str):
        return None
    # strip protocol suffix
    spec = entry.split("/")[0]
    parts = spec.split(":")
    if len(parts) == 2:
        return "0.0.0.0", parts[0]
    if len(parts) == 3:
        return parts[0], parts[1]
    return None


def check(doc: dict, check_paths: bool) -> list[Finding]:
    out: list[Finding] = []
    services = doc.get("services") or {}
    if not services:
        out.append(Finding("E001", "services", "no services defined"))
        return out

    volumes = doc.get("volumes") or {}
    used_volumes: set[str] = set()
    host_ports: dict[str, str] = {}

    for name, svc in services.items():
        svc = svc or {}
        where = f"services.{name}"

        if "image" not in svc and "build" not in svc:
            out.append(Finding("E001", where, "has neither image nor build"))

        image = svc.get("image")
        if image:
            tag = image.rsplit("/", 1)[-1]
            if ":" not in tag or tag.endswith(":latest"):
                out.append(Finding("W102", where, f"image '{image}' is unpinned or latest"))

        if "restart" not in svc:
            out.append(Finding("W103", where, "no restart policy"))

        ports = svc.get("ports") or []
        if ports and "healthcheck" not in svc:
            out.append(Finding("W104", where, "publishes ports but has no healthcheck"))

        for p in ports:
            parsed = parse_ports(p)
            if not parsed:
                continue
            host_ip, host_port = parsed
            key = f"{host_port}"
            if key in host_ports:
                out.append(Finding("E003", where,
                                   f"host port {host_port} already published by {host_ports[key]}"))
            else:
                host_ports[key] = name
            if host_ip in ("0.0.0.0", "::", ""):
                out.append(Finding("I201", where, f"port {host_port} binds on all interfaces"))

        # log rotation
        logging_cfg = svc.get("logging") or {}
        driver = logging_cfg.get("driver", "json-file")
        opts = logging_cfg.get("options") or {}
        if driver in UNBOUNDED_LOG_DRIVER and "max-size" not in opts:
            out.append(Finding("W105", where, f"log driver '{driver}' without max-size"))

        # volumes
        for v in svc.get("volumes") or []:
            if isinstance(v, dict):
                src, vtype = v.get("source"), v.get("type", "volume")
            else:
                src, _, rest = str(v).partition(":")
                vtype = "bind" if src.startswith(("/", ".", "~")) else "volume"
            if vtype == "volume" and src:
                used_volumes.add(src)
            elif vtype == "bind" and src and check_paths:
                expanded = os.path.abspath(os.path.expanduser(src))
                if not os.path.exists(expanded):
                    out.append(Finding("E002", where, f"bind source missing: {expanded}"))

        # env: list entries without "=" pass a host var straight through,
        # and ${VAR} references with no default are silent failures when unset
        env = svc.get("environment") or []
        if isinstance(env, list):
            for item in env:
                if not isinstance(item, str):
                    continue
                if "=" not in item:
                    out.append(Finding("W106", where, f"'{item}' : no default, fails silently if unset"))
                    continue
                key, _, val = item.partition("=")
                for ref in re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", val):
                    out.append(Finding("W106", where, f"'{key}' depends on ${{{ref}}} with no default"))
        elif isinstance(env, dict):
            for key, val in env.items():
                if val is None:
                    out.append(Finding("W106", where, f"'{key}' : no default, fails silently if unset"))

    for vol_name in volumes:
        if vol_name not in used_volumes:
            out.append(Finding("W101", f"volumes.{vol_name}", "declared but not used by any service"))

    return out


def load(path: str) -> dict:
    if path == "-":
        text = sys.stdin.read()
    else:
        text = open(path, encoding="utf-8").read()
    if yaml is not None:
        return yaml.safe_load(text) or {}
    raise SystemExit("PyYAML not installed; `pip install pyyaml`")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Static checks for docker compose files.")
    ap.add_argument("files", nargs="+", help="compose files to inspect")
    ap.add_argument("--check-paths", action="store_true",
                    help="also verify that bind-mount sources exist on this host")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--min-severity", choices=["info", "warn", "error"], default="info")
    args = ap.parse_args(argv)

    rank = {"info": 0, "warn": 1, "error": 2}
    all_findings: list[Finding] = []
    for path in args.files:
        try:
            doc = load(path)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"cannot parse {path}: {exc}", file=sys.stderr)
            return 2
        for f in check(doc, args.check_paths):
            f.where = f"{os.path.basename(path)}:{f.where}"
            all_findings.append(f)

    shown = [f for f in all_findings if rank[SEVERITY[f.code[0]]] >= rank[args.min_severity]]
    if args.json:
        print(json.dumps([{"code": f.code, "where": f.where, "message": f.message} for f in shown], indent=2))
    else:
        for f in shown:
            print(f)
        if not shown:
            print("clean")
    return 1 if any(f.code.startswith("E") for f in all_findings) else 0


if __name__ == "__main__":
    sys.exit(main())
