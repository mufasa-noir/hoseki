## Approval gate

The approval prompt runs in the daemon's own process, reading from
`stdin`/writing to `stderr`. Neither the model nor any file content can
inject into it. The gate is serialised: one prompt at a time, one answer.

Test hooks (`ApprovalGate.set_auto_for_tests`) exist for the test suite
only and are never reachable from HTTP, config, or file content.

## Docker sandbox

`run_cmd` runs inside a container with `--network=none`, `--cap-drop=ALL`,
`--security-opt=no-new-privileges`, and a read-only workspace mount by
default. If Docker is not available and `commands.unsafe_host_exec = false`,
`run_cmd` refuses. The `sandbox.mode = "refuse"` setting is a kill switch.

## Audit log

Every call — read, write, patch, and command — is appended as a JSON object
to `~/.hoseki/audit.jsonl`, including the resolved args, the approval
decision, and a short result summary. This is append-only, but a local
attacker with write access can of course tamper with it.