"""Deletion Policy Tool: A utility for managing file deletion based on configurable policies.

See the README.md for usage instructions.
"""

import dataclasses
import datetime
import logging
import logging.handlers
import os
import pathlib
import typing

import click
import decouple
import yaml

_logger = logging.getLogger(__name__)
_logger.addHandler(logging.NullHandler())


@dataclasses.dataclass(frozen=True, slots=True)
class DeletionPolicy:
    """Represents a deletion policy for managing files in a folder."""

    folder: pathlib.Path
    """Folder to examine for files to delete."""

    age: int
    """Delete files older than this many days (by modification time)."""

    delete_if_backed_up_to: pathlib.Path | None
    """(optional - default None) Delete files if they are backed up to this folder."""

    delete_if_copy_exists: typing.Tuple[str, str] | None
    """(optional - default None) Delete files that have been copied to a different
    extension in this same folder. The tuple is (source_extension, destination_extension)."""

    extension: str = ".*"
    """(optional - default '.*') File extension to match (e.g., '.mp4')."""


def _config_path(key: str, default: str | None = None) -> pathlib.Path:
    if default is None:
        return pathlib.Path(str(decouple.config(key)))

    return pathlib.Path(str(decouple.config(key, default=default)))


def _load_config() -> list[DeletionPolicy]:
    config_file = _config_path(
        "DELETION_POLICY_CONFIG_FILE", default="~/.config/deletion_policy.yml"
    ).expanduser()

    with config_file.open("r", encoding="utf-8") as config_stream:
        raw_config = yaml.load(config_stream, Loader=yaml.CSafeLoader) or []

    if isinstance(raw_config, dict):
        raise ValueError(
            f"Expected a list of policies in {config_file}, but got a dictionary. Please check the configuration format."
        )

    policies: list[DeletionPolicy] = []
    for policy_config in raw_config:
        delete_if_copy_exists = policy_config.get("delete_if_copy_exists")
        if delete_if_copy_exists:
            delete_if_copy_exists = tuple(delete_if_copy_exists)

        delete_if_backed_up_to = policy_config.get("delete_if_backed_up_to")
        if delete_if_backed_up_to:
            delete_if_backed_up_to = pathlib.Path(delete_if_backed_up_to).expanduser()

        policies.append(
            DeletionPolicy(
                folder=pathlib.Path(policy_config["folder"]).expanduser(),
                age=int(policy_config["age"]),
                delete_if_backed_up_to=delete_if_backed_up_to,
                delete_if_copy_exists=delete_if_copy_exists,
                extension=policy_config.get("extension", ".*"),
            )
        )

    return policies


TODAY = datetime.datetime.now()


def _iter_policy_files(policy: DeletionPolicy) -> typing.Iterator[pathlib.Path]:
    pattern = "*" if policy.extension == ".*" else f"*{policy.extension}"
    for file in policy.folder.rglob(pattern):
        if file.is_symlink():
            print(f"skipping {file}: symlink")
            continue
        if file.is_file():
            yield file


def _is_file_old(file: pathlib.Path, min_age_days: int) -> bool:
    file_age = datetime.datetime.now() - datetime.datetime.fromtimestamp(file.stat().st_mtime)
    return file_age >= datetime.timedelta(days=min_age_days)


def _has_backup_copy(file: pathlib.Path, policy: DeletionPolicy) -> bool:
    if policy.delete_if_backed_up_to is None:
        return True

    backup_file = policy.delete_if_backed_up_to / file.relative_to(policy.folder)
    return backup_file.is_file()


def _has_expected_copy(file: pathlib.Path, policy: DeletionPolicy) -> bool:
    if policy.delete_if_copy_exists is None:
        return True

    source_ext, dest_ext = policy.delete_if_copy_exists
    if file.suffix != source_ext:
        return False

    copy_file = file.with_suffix(dest_ext)
    return copy_file.is_file()


def _confirm_or_skip(
    path: pathlib.Path, *, action: str, dry_run: bool, confirm_each_delete: bool
) -> bool:
    if dry_run:
        print(f"would {action} {path}")
        return False

    if confirm_each_delete and not click.confirm(f"{action.capitalize()} {path}?", default=False):
        print(f"skipping {path}: user declined")
        return False

    print(f"{action} {path}")
    return True


def _process_policy(
    policy: DeletionPolicy, *, confirm_each_delete: bool = False, dry_run: bool = False
) -> None:
    for file in _iter_policy_files(policy):
        if not _is_file_old(file, policy.age):
            print(f"skipping {file}: less than {policy.age} days old")
            continue

        # using nested if statements to avoid logging if the skip is due to not using the parameter
        if policy.delete_if_backed_up_to is not None:
            if not _has_backup_copy(file, policy):
                print(f"skipping {file}: backup copy missing")
                continue

        if policy.delete_if_copy_exists is not None:
            if not _has_expected_copy(file, policy):
                print(f"skipping {file}: expected copy missing")
                continue

        if _confirm_or_skip(
            file,
            action="delete",
            dry_run=dry_run,
            confirm_each_delete=confirm_each_delete,
        ):
            file.unlink()


def _config_logging(verbosity: int):
    """Setup logging output.

    If verbosity is -1, logging is set to info warning
    0 = info
    1 = debug
    and so on

    Logging is also done to ~/logs/deletion_policy_tool.log with a rotating file handler.
    """
    verbosity = max(-1, verbosity)  # Ensure verbosity is at least -1
    verbosity = min(2, verbosity)  # Ensure verbosity is at most 2

    root_logger = logging.getLogger()
    if verbosity <= -1:
        root_logger.setLevel(logging.WARNING)
    elif verbosity == 0:
        root_logger.setLevel(logging.INFO)
    else:
        root_logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(handler)

    log_dir = pathlib.Path.home() / "logs"
    log_dir.mkdir(exist_ok=True, parents=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "deletion_policy_tool.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(file_handler)


@click.command()
@click.option(
    "--remove-empty-folders",
    is_flag=True,
    help="Remove empty folders after deleting files.",
)
@click.option(
    "--confirm-each-delete",
    is_flag=True,
    help="Request confirmation from the user before deleting each file/folder.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Do not take actions, only log what would happen.",
)
@click.option(
    "--verbose",
    "-v",
    multiple=True,
    is_flag=True,
    help="Increase the verbosity (can be repeated)",
)
@click.option(
    "--quiet",
    "-q",
    multiple=True,
    is_flag=True,
    help="Decrease the verbosity (can be repeated)",
)
@click.version_option()
def _main(
    remove_empty_folders: bool,
    confirm_each_delete: bool,
    dry_run: bool,
    verbose: typing.List[bool],
    quiet: typing.List[bool],
) -> None:
    verbose_count = len(verbose)
    quiet_count = len(quiet)
    if verbose_count > 0 and quiet_count > 0:
        raise click.UsageError("Cannot use both --verbose and --quiet options together.")
    verbosity = verbose_count - quiet_count
    _config_logging(verbosity=verbosity)
    policies = _load_config()
    for policy in policies:
        _process_policy(policy, confirm_each_delete=confirm_each_delete, dry_run=dry_run)

    if remove_empty_folders:
        for policy in policies:
            for folder, _, _ in os.walk(policy.folder, topdown=False):
                folder_path = pathlib.Path(folder)
                if not any(folder_path.iterdir()):
                    if _confirm_or_skip(
                        folder_path,
                        action="remove empty folder",
                        dry_run=dry_run,
                        confirm_each_delete=confirm_each_delete,
                    ):
                        folder_path.rmdir()


if __name__ == "__main__":
    _main()
