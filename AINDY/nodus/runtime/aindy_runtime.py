"""
AINDYNodusRuntime - NodusRuntime subclass with host_globals fix.

The pip-installed nodus package has a bug: NodusRuntime.run_source() accepts
host_globals but does not forward it to ModuleLoader. This means any object
injected via host_globals (including memory_bridge for the recall/remember
built-ins) is silently discarded.

AINDYNodusRuntime.run_source() overrides only the ModuleLoader construction
call to pass host_globals through. All other behavior is identical to the
upstream implementation.
"""
from __future__ import annotations

import os
import os as _os
import re

from nodus.builtins.nodus_builtins import BuiltinInfo
from nodus.result import Result, normalize_filename
from nodus.runtime.embedding import NodusRuntime
from nodus.runtime.errors import coerce_error
from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.sandbox import capture_output, configure_vm_limits
from nodus.vm.vm import VM

_STDLIB_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(__file__)),
    "stdlib",
)


class AINDYNodusRuntime(NodusRuntime):
    """NodusRuntime with host_globals correctly forwarded to ModuleLoader.

    Usage:
        rt = AINDYNodusRuntime()
        rt.register_function("set_state", ..., arity=2)
        result = rt.run_source(script, host_globals={"memory_bridge": bridge})
    """

    def __init__(self, **kwargs):
        if "project_root" not in kwargs:
            kwargs["project_root"] = _STDLIB_DIR if _os.path.isdir(_STDLIB_DIR) else None
        super().__init__(**kwargs)

    def register_function(self, name: str, fn, *, arity: int | tuple[int, ...] | None = None) -> None:
        super().register_function(name, fn, arity=arity)
        stdlib_aliases = {
            "recall_from": "__memory_stdlib_recall_from",
            "recall_all": "__memory_stdlib_recall_all",
            "share": "__memory_stdlib_share",
        }
        alias = stdlib_aliases.get(name)
        if alias:
            super().register_function(alias, fn, arity=arity)

    def run_source(
        self,
        source: str,
        *,
        filename: str | None = None,
        max_steps: int | None = None,
        timeout_ms: int | None = None,
        max_stdout_chars: int | None = None,
        optimize: bool = True,
        import_state: dict | None = None,
        debugger=None,
        max_frames: int | None = None,
        initial_globals: dict | None = None,
        host_globals: dict | None = None,
    ) -> dict:
        """Override of NodusRuntime.run_source that passes host_globals to
        ModuleLoader. This single change makes VM._get_memory_bridge() work
        correctly so recall(), remember(), suggest() etc. use the injected
        memory_bridge object.

        See NodusRuntime.run_source docstring for all parameter documentation.
        """
        self.last_emitted_events: list[dict] = []
        if "memory." in source:
            source = re.sub(
                r'(?m)^(\s*)import\s+"memory"\s*$',
                r'\1import "memory" as memory',
                source,
            )
            source = re.sub(
                r"(?m)^(\s*)import\s+memory\s*$",
                r'\1import "memory" as memory',
                source,
            )
        normalized = normalize_filename(filename)
        if import_state is None and self.project_root is not None:
            import_state = {
                "loaded": set(),
                "loading": set(),
                "exports": {},
                "modules": {},
                "module_ids": {},
                "project_root": self.project_root,
            }
        elif import_state is not None and self.project_root is not None:
            import_state["project_root"] = self.project_root

        vm = VM(
            [],
            {},
            code_locs=[],
            source_path=filename,
            allowed_paths=self.allowed_paths,
            module_globals=initial_globals,
            host_globals=host_globals,
        )
        if not self.allow_input:
            vm.input_fn = self._blocked_input
        if debugger is not None:
            vm.debugger = debugger
            vm.debug = True
        self.last_vm = vm
        host_builtins = {
            name: BuiltinInfo(
                info.name,
                info.arity,
                lambda *args, _fn=info.fn, _vm=vm: self._invoke_host_function(_vm, _fn, *args),
            )
            for name, info in self._host_functions.items()
        }

        resolved_steps = self.max_steps if max_steps is None else max_steps
        resolved_timeout = self.timeout_ms if timeout_ms is None else timeout_ms
        resolved_stdout = self.max_stdout_chars if max_stdout_chars is None else max_stdout_chars
        configure_vm_limits(vm, max_steps=resolved_steps, timeout_ms=resolved_timeout)
        resolved_frames = self.max_frames if max_frames is None else max_frames
        vm.max_frames = resolved_frames

        with capture_output(max_stdout_chars=resolved_stdout) as (stdout, stderr):
            try:
                loader = ModuleLoader(
                    project_root=self.project_root,
                    vm=vm,
                    host_builtins=host_builtins,
                    extra_builtins=set(self._host_functions.keys()),
                    host_globals=host_globals or {},
                    debugger=debugger,
                )
                if filename and os.path.isfile(filename):
                    loader.load_module_from_path(filename, auto_run_main=True)
                else:
                    loader.load_module_from_source(
                        source,
                        module_name=filename or "<memory>",
                        auto_run_main=True,
                    )
            except Exception as err:
                raise coerce_error(err, stage="execute", filename=normalized) from err

        # Extract user-emitted events from the VM's event bus.
        # Filter out internal Nodus VM instrumentation events.
        _INTERNAL_EVENT_PREFIXES = ("vm_", "runtime.", "nodus.")
        self.last_emitted_events = [
            e.to_dict()
            for e in vm.event_bus.events()
            if not any(e.type.startswith(p) for p in _INTERNAL_EVENT_PREFIXES)
        ]

        return Result.success(
            stage="execute",
            filename=normalized,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        ).to_dict()
