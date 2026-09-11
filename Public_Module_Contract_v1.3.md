# A Meo V1.3 Public Module Contract

This is the current official public contract for third-party A Meo modules.
It describes the boundary a module may rely on and the behavior required for
Plug-and-Play compatibility. It is written for a developer who has no
knowledge of A Meo's private implementation, and it is **complete and
self-contained** — a module author needs only this one document.

**V1.3 is a consolidation, not a new boundary.** It merges
`Public_Module_Contract_v1.1.md` (the original contract) and
`Public_Module_Contract_v1.2.md` (which added one optional field, additively)
into a single document for distribution. No behavior described here is new
relative to V1.2: every V1.1 module and every V1.2 module keeps working with
no change. `Public_Module_Contract_v1.1.md` and `Public_Module_Contract_v1.2.md`
are preserved unchanged as prior versions of record.

The current contract version is **V1.3**. A breaking change to the module
boundary requires a new contract version; the behavior documented here must
not change silently.

## 1. Scope and compatibility rule

An external module is a self-contained folder copied to:

```text
<project_root>/modules/<module_id>/
```

The folder is the module's complete installation unit. A module must not
require edits to A Meo files, configuration, release artifacts, or other
modules.

The Host discovers, checks, activates, and sends turns to the module through
the public boundary described here. A module failure must not make A Meo
unavailable.

Only the following are stable dependencies for a module:

- the folder and manifest rules;
- the `boot()` entry point;
- the public `BaseCapability` and `HubResponse` types;
- the `execute()` and `health_check()` surface;
- the `handle_turn` payload and response (including the optional
  `attachments` input and `artifacts` output described in §5);
- the `invoke()` Host API allowlist;
- the module-owned data directory;
- the scan, integrate, activate, switch, and deactivate behavior.

Anything else is private and must not be imported or relied upon.

## 2. Module package layout

The minimum layout is:

```text
modules/
└── <module_id>/
    ├── module_manifest.json   # required
    ├── boot.py                # default entry file
    └── ...                    # module-owned files
```

Optional folders include `data/`, `.venv/`, and `tests/`.

`<module_id>` must match the module folder name exactly. A module may use one
of two supported Python layouts:

1. Flat layout: no `__init__.py` at the module root. Files in the root use
   ordinary imports such as `from capability import MyCapability`.
2. Package layout: an `__init__.py` exists at the module root. The module may
   use normal package and relative imports such as
   `from .capability import MyCapability`.

The layout is selected by the presence of `__init__.py`; it is not a manifest
field.

Module code must be portable across Windows, macOS, and Linux by default:

- resolve module files from `Path(__file__).resolve().parent` or from the
  injected `module_data_root`;
- use `pathlib.Path` rather than hard-coded separators or string path joins;
- do not depend on the current working directory, a drive letter, or a fixed
  installation location;
- if an optional feature is OS-specific, detect that at runtime and disable
  it cleanly when unavailable.

See also §10 (Portability guarantees) for the rules covering attachment
paths specifically.

## 3. Manifest

Every module must contain `module_manifest.json` at its root. The Host reads
the manifest during scanning without running module business code.

Supported fields are:

| Field | Required | Type | Meaning |
|---|---:|---|---|
| `module_id` | No (recommended) | string | Module identifier. When present, it must equal the containing folder name. If omitted, the folder name is used. A mismatched value causes the module to be skipped. |
| `description` | No | string | Human-readable purpose shown by the Host. Missing means an empty description. |
| `version` | No | string | Module version for display and reference. It is not compatibility-validated by the Host. |
| `entry_file` | No | string | Entry file name relative to the module folder. Default: `boot.py`. |
| `requirements` | No | array of strings | Declarative Python package requirements. The Host does not install them. |

Unknown fields are ignored. This contract does not define a `contract_version`
or `os_requirements` manifest field.

Minimal example:

```json
{
  "module_id": "my_module",
  "description": "A small example module.",
  "version": "0.1.0",
  "entry_file": "boot.py",
  "requirements": []
}
```

## 4. Entry point and capability surface

The manifest entry file must define a synchronous function named `boot`.
The Host calls it when validating or starting the module.

Two signatures are supported:

```python
def boot() -> BaseCapability:
    ...
```

```python
def boot(invoke, module_data_root: Path) -> BaseCapability:
    ...
```

The parameter names are part of the contract. The Host recognizes only
`invoke` and `module_data_root` and supplies only the parameters declared by
the function. `boot()` must not be asynchronous, and this contract defines no
third injected parameter.

`module_data_root` is a `pathlib.Path` owned by the module. It points to the
module's persistent data directory and is created by the Host when needed.

`invoke` is an asynchronous callable:

```python
async def invoke(capability: str, action: str, payload: dict) -> HubResponse:
    ...
```

It is the only supported way for module code to call a Host service.

The only A Meo Python types a module needs to import are the public types
shown below:

```python
from src.core.hub.contracts import BaseCapability, HubResponse
```

That import is the published compatibility import. Do not import any other
A Meo Python module or singleton.

The public type surface is:

```python
class BaseCapability(ABC):
    @property
    @abstractmethod
    def capability_name(self) -> str: ...

    @abstractmethod
    async def execute(
        self, action: str, payload: Dict[str, Any]
    ) -> HubResponse: ...

    def health_check(self) -> bool:
        return True


class HubResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
```

Requirements:

- `boot()` returns one `BaseCapability` instance.
- `capability_name` returns exactly the manifest `module_id` and folder name.
- `execute()` is an `async def` coroutine.
- `health_check()` is synchronous and returns `True` or `False`.
- A false or failing health check makes boot fail.
- Unknown actions should return `HubResponse(success=False, error=...)`.
- Business errors should normally be caught by the module and returned as a
  controlled response. A raw exception is caught at the boundary and treated
  as a module failure.

## 5. Handling user turns

The module receives a turn through:

```python
await capability.execute("handle_turn", {
    "text": "the user's original message",
    "user_id": "user identifier"
})
```

The base payload fields are:

| Field | Type | Meaning |
|---|---|---|
| `text` | string | The user's original message, passed without Host keyword classification. |
| `user_id` | string | An opaque user identifier. The module decides how to use it. |

For a supported turn, return:

```python
HubResponse(success=True, data={
    "consumed": True,
    "response": "text shown to the user"
})
```

`data.consumed` is required for a successful turn response:

- `True`: the module handled the turn and the Host should finish the turn
  with this module's response;
- `False` or missing: the module does not claim the turn and the Host may
  continue with its normal conversation pipeline.

`data.response` should be a string when `consumed` is `True`. Additional data
fields are allowed and are passed through as part of the response.

The Host sends a module turn only when all of these are true:

1. request mode is `WORKING`;
2. exactly one module is active;
3. that active module is this module;
4. the module is available.

`CHAT` and `COMPUTER` mode requests do not invoke the module. A dormant or
unexpectedly stopped module is skipped and the Host continues safely.

### 5.1 Attachments (optional input)

The payload MAY also carry `attachments` when the user's turn included one
or more files / media (from the Electron GUI or Telegram — the module is
never told which; it is still just "the current turn"):

```python
{
  "text": "the user's original message",
  "user_id": "user identifier",
  "attachments": [
    {
      "attachment_id": "<opaque id>",
      "filename": "report.pdf",          # sanitised basename, display only
      "mime_type": "application/pdf",
      "size_bytes": 183245,
      "type": "image|video|audio|document|file",
      "reference": "att:<attachment_id>", # Host-managed, opaque
      "path": "<runtime-provided absolute path>",  # read-only, this turn only
      "metadata": {}
    }
  ]
}
```

Rules:

- `attachments` is **optional**. Absent or `[]` ⇒ identical to a plain
  `text`/`user_id` payload. A module is **not required** to support
  attachments; ignoring the key is a correct, conformant implementation.
- The list is ordered as the user supplied the files.
- `reference` is the stable, Host-managed identifier for the attachment. It
  is opaque — do not parse it, do not construct one, do not persist it
  beyond the turn.
- `path` is a convenience the Host resolves **at call time** for the
  current turn: a real, readable path to the attachment file on this
  machine. Open it **read-only**. Do **not**:
  - hard-code it, store it, or derive other paths from it;
  - assume any particular directory, drive letter, or separator — always
    go through `pathlib.Path(item["path"])` / `open(item["path"], "rb")`;
  - use it to reach any file other than that attachment.
- The file is guaranteed valid for the duration of the `handle_turn` call.
  A long-running module (background task pattern) may keep reading it while
  its `WorkSession` is `RUNNING`; it is cleaned up when Core shuts down. Do
  not rely on it after your task reports a terminal result.
- Reader-extractable document text (`.txt/.md/.pdf/.docx/.xlsx/.xls/.doc`)
  is **already folded into `text`** by the Host for CHAT-mode turns. In
  WORKING mode (i.e. when your module receives the turn) the Host does
  **not** pre-extract — your module gets the raw file via `path` and
  decides what to do with it.
- Unknown future keys on an attachment item must be ignored (forward
  compatible), same discipline as the rest of this contract.

### 5.2 Artifact output (optional output)

A module that produces a file / image / media result returns it the same
way as any other response: additional `data` fields on the `handle_turn`
response are passed through, and an `artifacts` list in `data` is picked up
by the Host and delivered to whichever channel the user is on (GUI or
Telegram) — the module still knows nothing about channels.

Each artifact is a plain dict:

```python
{
  "artifact_id": "<id>",
  "type": "image|file|video|audio|document",
  "mime_type": "image/png",
  "filename": "chart.png",
  "size_bytes": 12345,
  "data_base64": "<...>",   # small results
  # OR, for large / media results, instead of data_base64:
  "reference": "att:<id>",  # a Host runtime reference
  "metadata": {}
}
```

- Small results: inline `data_base64` (an 8 MB inline ceiling applies).
- Large / media results: set `reference` instead of `data_base64`. Obtain
  a reference by handing bytes to the Host — a module that needs this can
  request the minimal host helper; until then, `data_base64` under 8 MB is
  the supported path. Channel dispatch (GUI preview / `sendPhoto` /
  `sendVideo` / `sendDocument`) keys on `mime_type`, so `type:"file"` plus
  a correct `mime_type` is always sufficient.

## 6. Scan, integrate, and activation

The normal Plug-and-Play sequence is:

1. Copy the complete module folder into `modules/<module_id>/`.
2. Scan modules. Scanning reads manifests and does not run business code.
3. Integrate the module. The Host validates it by running `boot()` and the
   health check.
4. Activate the integrated module. The Host starts the module for subsequent
   turns.

Newly copied modules are not automatically discovered at startup. Previously
integrated modules may be restored without a new scan, and the last
successfully active module may be restored automatically when its persisted
state is valid.

### 6.1 Scan

The public Host action is:

```json
{"target":"module_manager","action":"scan_modules","payload":{}}
```

The module must be discoverable by its manifest and matching folder name.

### 6.2 Integrate

The public Host action is:

```json
{"target":"module_manager","action":"integrate_module","payload":{"module_id":"my_module"}}
```

Integration validates the entry point, `boot()`, capability name, and health
check. It does not install dependencies or modify the Host. Integration is
idempotent: integrating an already integrated module returns success without
requiring another validation run.

If boot or health checking fails, integration fails and the module is not
marked integrated. The error is reported as a controlled failure; the Host
remains available.

### 6.3 Activate, switch, and deactivate

Activation requires prior integration:

```json
{"target":"module_manager","action":"activate_module","payload":{"module_id":"my_module"}}
```

The module becomes active only after it has booted successfully.

At most one module is active at a time. When switching from module A to
module B, B must boot successfully before A is stopped and B is marked active.
If B cannot boot, A remains the active module.

To stop the active module:

```json
{"target":"module_manager","action":"deactivate_module","payload":{}}
```

Deactivation leaves the Host running and makes the active module empty. A
module must not assume that it remains available after deactivation or a
switch.

Read-only status actions are:

```json
{"target":"module_manager","action":"list_modules","payload":{}}
{"target":"module_manager","action":"get_active_module","payload":{}}
```

## 7. Host API available through `invoke()`

The following and only the following capability/action pairs are available to
module code through the injected `invoke()` callable.

| Capability | Action | Request payload | Successful response data |
|---|---|---|---|
| `conversation` | `chat` | `{"text": string, "system_prompt"?: string}` | `{"response": string}` |
| `knowledge_source_manager` | `list_workspaces` | `{}` | Workspace list. |
| `knowledge_source_manager` | `plan_for_purpose` | Service-specific payload. | A source-selection plan. |
| `knowledge_source_manager` | `list_folders` | `{"source_id": string}` | Folder list; folder entries may provide a `path`. |
| `knowledge_source_manager` | `get_runtime_context` | `{}` | `{"runtime_context": {"active_source_id": ...}}` when a source is selected. |
| `operating_context` | `get_reindex_status` | `{}` | `{"state": string}`. |

Example:

```python
response = await invoke(
    "conversation",
    "chat",
    {"text": "Summarize the current task."},
)
if response.success:
    answer = (response.data or {}).get("response", "")
else:
    answer = "The Host service was unavailable."
```

An unsupported capability/action pair returns a failed Host result. Module
code must handle `success == False`, missing data, and an invocation exception
without crashing the module's user-facing turn.

The module must not import a Host singleton or private capability
implementation. `invoke()` is the complete Host-service surface.

## 8. Module-owned data and restart behavior

The Host provides one persistent directory per module through
`module_data_root`, normally represented as:

```text
modules/<module_id>/data/
```

The module owns the contents of this directory. Use it for state that must
survive module restarts, deactivation, reactivation, or A Meo restart.

This contract provides no shared module database, key-value store, or
persistence API. The module defines its own file formats, migration rules,
and restart semantics. There is no module cleanup/shutdown callback. Persist
important state during normal operation rather than relying on shutdown-time
cleanup.

New module data must not be written into Host source or configuration files.
An upgrade must not delete user data by default.

## 9. Dependencies

The Host uses its current Python interpreter for a module unless the module
provides its own virtual environment. A module-local `.venv` is optional and,
when present in the supported layout, is preferred for running that module.

The module author is responsible for creating the environment and installing
the packages listed in `requirements`. The Host does not run pip, mutate its
own environment, or resolve dependency conflicts for the module.

A module that needs only Python and packages already available to the selected
interpreter may omit `.venv` and use an empty `requirements` list.

## 10. Portability guarantees

- A module must remain Plug-and-Play, path-independent and OS-independent
  (see also §2).
- The only attachment identifiers in the public contract are
  `attachment_id` and `reference`. `path` (§5.1) is a runtime convenience,
  not a contract surface — a future Host release may replace it with a
  host-call accessor; a module that treats `path` as read-only and
  turn-scoped will not break.
- No absolute Host path, drive letter, cwd assumption, or `modules/`
  sibling path may be baked into module code.

## 11. Failure and safety obligations

The module author is responsible for:

- domain routing inside `handle_turn`;
- validation and business rules;
- pending workflow state and persistence;
- graceful, user-meaningful error responses;
- closing module-owned resources during normal operation;
- keeping important state on disk rather than only in memory;
- ensuring module files and assets are path-agnostic.

The module must not:

- patch or require edits to A Meo source, configuration, or release files;
- install itself into another module or into a Host capability directory;
- import private A Meo code, private singletons, or another module's internals;
- hard-code an A Meo installation path or current working directory;
- assume that activation lasts forever;
- activate itself or assume another module exists;
- add GUI tabs, Telegram-specific extensions, or Computer Mode features to
  this contract (attachment/media *input and output* are supported per §5;
  interpreting their content is not — see §14).

If `execute()` fails, the Host contains the failure. A failed response or a
module becoming unavailable does not make A Meo unavailable; the affected
turn is treated as unconsumed and can continue through the normal Host
pipeline.

## 12. Minimal complete example

This flat-layout example is sufficient for a small module.

`module_manifest.json`:

```json
{
  "module_id": "my_module",
  "description": "Returns a response for messages mentioning my_module.",
  "version": "0.1.0",
  "entry_file": "boot.py",
  "requirements": []
}
```

`capability.py`:

```python
from typing import Any, Dict

from src.core.hub.contracts import BaseCapability, HubResponse


class MyModuleCapability(BaseCapability):
    @property
    def capability_name(self) -> str:
        return "my_module"

    async def execute(self, action: str, payload: Dict[str, Any]) -> HubResponse:
        if action != "handle_turn":
            return HubResponse(success=False, error=f"Unsupported action: {action}")

        text = payload.get("text") or ""
        if "my_module" not in text.lower():
            return HubResponse(success=True, data={"consumed": False})

        return HubResponse(
            success=True,
            data={
                "consumed": True,
                "response": f"my_module received: {text}",
            },
        )

    def health_check(self) -> bool:
        return True
```

`boot.py`:

```python
from src.core.hub.contracts import BaseCapability

from capability import MyModuleCapability


def boot() -> BaseCapability:
    return MyModuleCapability()
```

For a package-layout module, add `__init__.py` and change the local import to
`from .capability import MyModuleCapability`. For a module that needs Host
services or persistent data, use the full boot signature:

```python
from pathlib import Path

from src.core.hub.contracts import BaseCapability

from .capability import MyModuleCapability


def boot(invoke, module_data_root: Path) -> BaseCapability:
    return MyModuleCapability(invoke, module_data_root)
```

## 13. Compatibility checklist

Before distribution, confirm that:

- the folder name, manifest `module_id`, and `capability_name` are identical;
- the manifest and entry file are present;
- `boot()` has one of the supported signatures and returns a capability;
- `execute()` is asynchronous and returns `HubResponse` for every action;
- `health_check()` is synchronous and truthful;
- `handle_turn` reads `text` and `user_id` and returns `consumed`;
- if the module reads `attachments`, it tolerates the key being absent;
- attachment files (§5.1) are opened read-only and not retained past the
  turn's terminal result;
- `path` is never hard-coded, stored, or used to reach other files;
- artifact output (§5.2) uses the Artifact dict shape (inline `data_base64`,
  or `reference` for large/media);
- Host calls are limited to the documented `invoke()` allowlist;
- important data is stored below `module_data_root`;
- imports and paths still work after moving the module to another folder or
  machine;
- no file outside the module folder is required to be changed;
- the module behaves correctly when it is not active, when a turn is in
  `CHAT` mode, and after a module restart.

## 14. Boundary exclusions (still out of scope)

This contract intentionally covers only the currently supported module
boundary. It does not define:

- module-specific GUI extensions or tabs;
- module-specific Telegram integration behavior;
- Computer Mode features;
- multimodal AI understanding of image/video/audio content — the Host
  accepts and forwards such files (§5.1) and delivers module-produced media
  (§5.2); it does not interpret their content;
- OCR / STT / media-generation frameworks.

Attachment/media *input and output* (§5.1, §5.2) are supported, additive
since V1.2; everything else above remains excluded as it was under V1.1.
