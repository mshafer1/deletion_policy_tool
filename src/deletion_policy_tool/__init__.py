import dataclasses
import datetime
import os
import pathlib
import typing

import click
import decouple
import yaml


@dataclasses.dataclass(frozen=True, slots=True)
class DeletionPolicy:
    folder: pathlib.Path
    """Folder to examine for files to delete."""

    age: int
    """Delete files older than this many days (by modification time)."""

    delete_if_backed_up_to: pathlib.Path | None
    """(optional - default None) Delete files if they are backed up to this folder."""

    delete_if_copy_exists: typing.Tuple[str, str] | None
    """(optional - default None) Delete files that have been copied to a different extension in this same folder. The tuple is (source_extension, destination_extension)."""

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


def _process_policy(policy: DeletionPolicy) -> None:
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

        print(f"deleting {file}")
        file.unlink()


@click.command()
@click.option(
    "--remove-empty-folders", is_flag=True, help="Remove empty folders after deleting files."
)
def _main(remove_empty_folders: bool) -> None:
    policies = _load_config()
    for policy in policies:
        _process_policy(policy)

    if remove_empty_folders:
        for policy in policies:
            for folder, _, _ in os.walk(policy.folder, topdown=False):
                folder_path = pathlib.Path(folder)
                if not any(folder_path.iterdir()):
                    print(f"removing empty folder {folder_path}")
                    folder_path.rmdir()


if __name__ == "__main__":
    _main()
