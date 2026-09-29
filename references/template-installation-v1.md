# Offline Python template package and installation v1

The first installed-host profile is Linux x86-64 CPython 3.13, a private
owner-selected directory, pip and a setuptools PEP 517 wheel with a declared
`[project.scripts]` console entry. It accepts a host that was **already applied
and independently verified** by the implementation lifecycle. The package
planner never applies a source patch. Build hooks and pip run only after
separate exact-plan approvals. The host runtime stays off; an installation
receipt does not establish launch, provider reachability, authority, or benefit.

The public API is `plan_package`, `build_package`, `package_status`, `recover_package`,
`plan_install`, `install_package`, `installation_status`, and
`recover_installation` in `jev_integration_evaluator.template_installation`.
Corresponding `jev-integration-evaluator template` CLI actions are `package`,
`package-build`, `package-status`, `package-recover`, `install-plan`, `install`, `install-status`,
and `install-recover`. Existing catalog actions and legacy receipts are unchanged.
Every plan and receipt has schema version `1.0`, strict public and packaged
schemas, and a canonical SHA-256 seal. A seal detects accidental or unauthorized
local changes when compared with an independently retained digest; a local seal
alone is not caller authority.

## Inputs and commands

Create a private JSON request conforming to
[`template-package-request-v1`](../schemas/template-package-request-v1.schema.json).
Its exact fields are:

| Field | Meaning |
|---|---|
| `host_root` | Pre-applied host source root; every included regular file is hashed. Symlinks and oversize trees fail. |
| `implementation_bundle`, `trusted_modified_receipt_sha256` | Existing implementation bundle and a modified verification receipt digest retained independently of that bundle. `implementation_status` must return `verified` with externally anchored execution. |
| `template_directory` | Completed #51 materialization. Its lock, marker, spec, resource hashes, and candidate must match the implementation bundle. |
| `reviewed_package_source_sha256` | Independently reviewed digest of the current full package-source file map. This covers the packaging metadata and console module in addition to the implementation's reviewed seam. |
| `interpreter` | Exact current CPython 3.13 executable. The plan binds its binary SHA-256, Python patch version, SOABI and platform. |
| `build_tools` | Exact installed `pip`, `setuptools`, and `wheel` versions. The host `pyproject.toml` must pin setuptools and wheel in `build-system.requires`. |
| `wheelhouse`, `wheels`, `requirements` | Existing wheelhouse with SHA-256 for every wheel and a fully resolved name/version/wheel/hash row for every dependency, including the evaluator and build tools. Wheel tags must match the interpreter/platform; package metadata must match lock rows. |
| `package_directory`, `environment_parent` | New package output and existing owner-private environment parent, both outside the host. One install generation is derived from the install-plan digest. |
| `console_script`, `configuration`, `reviewed_configuration_sha256`, `secret_references` | Declared console entry, strict off-mode JSON config and independent digest, plus `env:NAME` references only. A live secret value is never required to install off mode. |

The commands below require real private paths and externally retained digests;
they are a sequence illustration, not an approval shortcut:

```bash
jev-integration-evaluator template package --request /private/package-request.json --out /private/package-plan.json
jev-integration-evaluator template package-build --plan /private/package-plan.json --approve-plan-sha256 EXACT_REVIEWED_PACKAGE_PLAN_DIGEST
jev-integration-evaluator template install-plan --package-plan /private/package-plan.json --package-receipt /private/package/package-receipt.json --out /private/install-plan.json
jev-integration-evaluator template install --plan /private/install-plan.json --approve-plan-sha256 EXACT_REVIEWED_INSTALL_PLAN_DIGEST
jev-integration-evaluator template install-status --plan /private/install-plan.json
```

`package` and `install-plan` only read and write external plan files. `package-build`
copies reviewed source into a private build staging directory and builds one
wheel using the pinned, current build tools with pip index access disabled.
The host wheel must be pure Python. A wheel digest cannot exist before the
build hook runs, so the package receipt records it after the effect.
`install` creates a new private venv, installs exact wheel hashes with pip
`--require-hashes --no-index`, installs the host wheel without dependency
resolution, runs `pip check`, verifies distribution RECORD hashes and origins,
checks the declared console entry target in an isolated interpreter, and writes
off-mode config. No user/global site package is installed. A launch or readiness
claim belongs to #56; the installer does not run the console entry itself.

Build/install subprocesses receive a narrow environment with no inherited
`PIP_*`, `PYTHONPATH`, user site or pip config. Package acquisition is a
separate operation; `scripts/prepare_template_wheelhouse.py` is an explicit
network-capable CI/test preparation command, never called by a planner or
installer. Prebuilt compatible native dependency wheels can be used after
tag/hash/metadata checks. Building an arbitrary native host extension is
outside this first profile. Poetry, uv, Conda, editable production installs,
containers and cloud installers are unsupported.

## Identity, recovery, and upgrade

Package and environment directories are exclusively created, owner-private,
and protected by nonblocking POSIX locks. Each has an append-only hash-chain
effect journal with stage intent and completion events. A repeated call with
the same plan adopts only an exact verified receipt and current installed
files; it never blindly repeats pip or build hooks. A pending build without a
receipt blocks replay. An interrupted install without a receipt blocks replay.
Receipt write followed by a missing terminal journal event can be adopted only
after the wheel or installed bytes pass current verification.

`package-recover` and `install-recover` can adopt proven completed outputs. To
remove an incomplete generation, first inspect the directory and its
`generation_sha256` from `install-status` or `package-status`, then supply that
exact independently reviewed digest via
`--approve-generation-sha256`. Recovery rechecks the tree, ownership, journal,
mounts, links, and known top-level contents before removing only the exact
owned directory. Build hook effects outside that directory cannot be proven
absent; an interrupted build needs operator review before its output is removed
or a fresh build is authorized. A changed or unknown entry is retained and
reported as blocked. Sibling environments and files are untouched.

The #56 supervisor should retain the template lock SHA, implementation bundle
digest and externally trusted verification receipt SHA, package/install plan
and receipt SHAs, full source hash, interpreter binary/ABI/platform, host wheel
SHA, dependency wheel hashes, config and secret-reference digests, generation
ID/path, installed RECORD digest, console target origin and journal head. It
must separately supervise launch, readiness, integration reachability,
connected-mode authority, stop and rollback. For upgrade, prepare a fresh
source-bound package and a new install plan; the resulting generation name
changes. The previous verified environment stays in place for #56 rollback.
Incompatible schema or lock versions require an explicit migration; there is
no in-place guess or automatic exposure expansion.

The Linux installed-host test uses an independently authored synthetic fixture
and an explicitly prepared wheelhouse. It confirms package metadata, import
origin, a real console launch, interruption recovery and sibling preservation.
These are offline synthetic qualification results, not live provider or
observed-benefit evidence.
