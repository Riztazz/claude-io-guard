"""Everything a check may read: the config, the probe, the platform, and ports to git, files and the clock.

A check receives a Context and reads it. No check writes into it except the session state, through its typed
fields. Context.live builds the real ports, and Context.fake builds in-memory ones for tests.
"""
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ioguard.lib.config import (Config, ConfigKey, LoadReport, Scope, all_keys, config_layers, defaults, load,
                                trusted)
from ioguard.lib.git import Git
from ioguard.lib.platform import Platform, detect
from ioguard.lib.ports import Clock, FsPort, GitPort, LiveFs, SystemClock
from ioguard.lib.probing import Probe, load_probe
from ioguard.lib.session import SessionState
from ioguard.lib.telemetry import Telemetry


@dataclass(frozen=True)
class Context:
    config: Config
    probe: Probe
    platform: Platform
    git: GitPort
    fs: FsPort
    clock: Clock
    session: SessionState
    telemetry: Telemetry
    config_report: LoadReport | None = None
    env: Mapping[str, str] = field(default_factory=dict)   # the environment, so no check reads os.environ
    data_dir: Path | None = None                           # io-guard's folder, None in a fake or a replay
    project: Path | None = None                            # the root whose layers config holds
    outside: Config | None = None                          # the config without the project's layers
    held: Mapping[str, Any] = field(default_factory=dict)  # the project's commands the user has not approved
    keys: Mapping[str, ConfigKey] = field(default_factory=lambda: all_keys({}))   # each setting, by its key

    @classmethod
    def live(cls, data_dir: Path | None, project: Path,
             check_keys: Mapping[str, Mapping[str, ConfigKey]] | None = None) -> Context:
        """The real ports, the config from its layers, and the probe from io-guard's folder. With no folder
        there is no user layer and no probe, and telemetry stays in memory. The project's commands join the
        config once the user approved them in trust.json, and wait in held until then."""
        platform = detect()
        layers = config_layers(data_dir, project)
        user = tuple(layer for layer in layers if layer.scope is Scope.USER)
        report = load(layers, check_keys or {})
        config, held = trusted(report, data_dir, project)
        return cls(config=config, probe=load_probe(data_dir, platform), platform=platform, git=Git(),
                   fs=LiveFs(), clock=SystemClock(), session=SessionState(),
                   telemetry=Telemetry(data_dir, enabled=config.get("telemetry.enabled")),
                   config_report=report, env=MappingProxyType(dict(os.environ)), data_dir=data_dir,
                   project=project, outside=load(user, check_keys or {}).config, held=held,
                   keys=all_keys(check_keys or {}))

    def for_file(self, path: Path | None) -> Context:
        """This context for a call on path: a file outside the project takes the config without the
        project's layers, and none of the project's commands waiting for approval, so one project's rules
        never govern another's files."""
        if path is None or self.project is None or self.outside is None or path.is_relative_to(self.project):
            return self
        return replace(self, config=self.outside, held={})

    def project_name(self, cwd: Path) -> str | None:
        """The project a telemetry line names: the root's folder name, else the working folder's."""
        return (self.project or cwd).name or None

    @classmethod
    def fake(cls, files: Mapping[Path, bytes] | None = None, **overrides: Any) -> Context:
        """In-memory ports for a test: a fake file system holding files, a fake git and a clock that only
        moves when told. Any field can be replaced by name."""
        from ioguard.lib.fakes import FakeClock, FakeFs, FakeGit
        platform = overrides.pop("platform", detect())
        built = dict(config=defaults(), probe=Probe.unprobed(platform), platform=platform, git=FakeGit(),
                     fs=FakeFs(files or {}), clock=FakeClock(), session=SessionState(),
                     telemetry=Telemetry.memory())
        built.update(overrides)
        return cls(**built)
