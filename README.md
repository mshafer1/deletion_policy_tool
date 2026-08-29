# deletion-policy-tool

This project provides a small command-line tool for cleaning up files according to configurable deletion policies.

## What it does

The tool scans one or more folders for files that match a policy, deletes them when they are old enough, and only removes them when any extra safety conditions are satisfied.

Each policy can require that a file:

- is older than a specified number of days,
- has the expected file extension,
- has a backup copy in a designated backup folder, and/or
- has a related copy with a different suffix in the same folder.

This makes it useful for retention workflows where files should be removed only after they have been preserved elsewhere.

## How it works

The CLI reads a YAML configuration file from the environment variable `DELETION_POLICY_CONFIG_FILE`.

Each entry in the YAML file is a policy with the following fields:

- `folder`: the directory to scan recursively
- `age`: minimum age in days before a file may be deleted
- `extension`: optional file extension to match (for example `.txt`)
- `delete_if_backed_up_to`: optional backup folder that must contain the same relative path
- `delete_if_copy_exists`: optional pair of extensions such as `['.txt', '.new_suffix']` meaning a file with the first extension must have a sibling with the second extension before deletion

Files are processed recursively under the configured folder. Only regular files are considered.

## Example configuration

```yaml
- folder: /path/to/source
  age: 30
  extension: .txt
  delete_if_backed_up_to: /path/to/backup

# deletes .log files if .bak file with same name exists next to it
- folder: /path/to/source
  age: 14
  extension: .log
  delete_if_copy_exists: [.log, .bak]
```

## Installation

### pipx

```bash
pipx install deletion_policy_tool
```

### global pip install (not recommended)

```bash
python -m pip install deletion_policy_tool
```

### uv

```bash
uv tool install deletion_policy_tool
```

### from source

```bash
git clone https://github.com/mshafer1/deletion_policy_tool.git
cd deletion_policy_tool
poetry install
```

## Usage

Set the configuration path and run the CLI:

```bash
export DELETION_POLICY_CONFIG_FILE=/path/to/deletion_policy.yml
run-deletion-policy
```

```bash
# use default policy (in ~/.config/deletion_policy.yml)
# also remove directories that are empty after files are deleted
run-deletion-policy --remove-empty-folders
```

```bash
# preview deletions without removing anything
run-deletion-policy --dry-run
```

```bash
# ask for confirmation before deleting each matching file or folder
run-deletion-policy --confirm-each-delete
```

```bash
# see all options
run-deletion-policy --help
```

### Optional flags

- `--dry-run`: logs the files and folders that would be deleted without making any changes.
- `--confirm-each-delete`: prompts the user before each deletion so you can review the action individually.
- `--remove-empty-folders`: removes directories that are empty after file deletions.
- `-v`: increases log verbosity. The default logging level is `INFO`; repeating `-v` raises the level to `DEBUG` so more detail is shown while policies are evaluated.

### Logging behavior

The CLI sets up logging as soon as it starts. Messages are emitted to the console and also written to a rotating log file at `~/logs/deletion_policy_tool.log`.

- Console logging follows the configured verbosity level.
- The default level is `INFO`.
- Each additional `-v` flag increases logging detail until `DEBUG` is reached.
- The file log uses a rotating handler with a 10 MiB limit and keeps the last 5 log files.

This makes it easier to troubleshoot policy matching and file-skipping decisions while still keeping a persistent history of runs.


If you are using the package entry point installed by Poetry, the command can also be run as:

```bash
poetry run deletion-policy-tool
```

## Notes

- The tool deletes files only after all applicable conditions pass.
- If a policy specifies a backup location, the backup file must exist at the same relative path under that backup folder.
- If a policy specifies a copy relationship, the corresponding file with the destination extension must exist.
- The tool is intentionally conservative: files are skipped unless the policy requirements are met.
