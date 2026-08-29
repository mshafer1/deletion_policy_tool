import difflib
import os
import time

import click.testing
import pytest
import yaml

import deletion_policy_tool


@pytest.fixture()
def example_folder(tmp_path):
    folder = tmp_path / "example"
    folder.mkdir()
    backup_folder = tmp_path / "backup"
    backup_folder.mkdir()

    normal_age = time.time() - (1 * 24 * 60 * 60)
    for i in range(5):
        file = folder / "nested_folder" / f"file_{i}.txt"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"example content {i}")
        os.utime(file, (normal_age, normal_age))

    for i in range(5):
        file = folder / f"file_with_different_extension_{i}.log"
        file.write_text(f"example content {i}")
        os.utime(file, (normal_age, normal_age))

    old_time = time.time() - (30 * 24 * 60 * 60)
    for i in range(5, 10):
        file = folder / f"old_file_{i}.txt"
        file.write_text(f"example content {i}")
        os.utime(file, (old_time, old_time))

    # create files that have copies
    for i in range(10, 15):
        file = folder / f"file_with_copy_{i}.txt"
        file.write_text(f"example content {i}")
        copy_file = folder / f"file_with_copy_{i}.new_suffix"
        copy_file.write_text(f"copy of example content {i}")
        os.utime(file, (normal_age, normal_age))
        os.utime(copy_file, (normal_age, normal_age))

    # create files that have backups
    for i in range(15, 20):
        file = folder / f"file_with_backup_{i}.txt"
        file.write_text(f"example content {i}")
        backup_file = backup_folder / f"file_with_backup_{i}.txt"
        backup_file.write_text(f"backup of example content {i}")
        os.utime(backup_file, (normal_age, normal_age))
        os.utime(file, (normal_age, normal_age))

    # nested files with backups
    for i in range(20, 25):
        file = folder / "nested_folder" / "backed_up" / f"nested_file_with_backup_{i}.txt"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"example content {i}")
        backup_file = (
            backup_folder / "nested_folder" / "backed_up" / f"nested_file_with_backup_{i}.txt"
        )
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        backup_file.write_text(f"backup of example content {i}")
        os.utime(backup_file, (normal_age, normal_age))
        os.utime(file, (normal_age, normal_age))

    return folder


def run_main_cli(tmp_path, policies, args=None):
    config_file = tmp_path / "deletion_policy.yml"
    config_file.write_text(yaml.safe_dump(policies), encoding="utf-8")

    result = click.testing.CliRunner().invoke(
        deletion_policy_tool._main,
        env={"DELETION_POLICY_CONFIG_FILE": str(config_file)},
        catch_exceptions=False,
        args=args or [],
    )

    assert result.exit_code == 0

    return result


def remaining_relative_paths(folder):
    return sorted(
        file.relative_to(folder).as_posix() + ("" if file.is_file() else "/")
        for file in folder.rglob("*")
    )


@pytest.mark.parametrize(
    ("args", "expected_verbosity"),
    [
        ([], 0),
        (["-v"], 1),
        (["-v", "-v"], 2),
        (["-q"], -1),
        (["-q", "-q"], -2),
    ],
)
def test___verbosity_flags___main___passes_expected_verbosity_to_config_logging(
    monkeypatch, args, expected_verbosity
):
    captured = {}

    monkeypatch.setattr(deletion_policy_tool, "_load_config", lambda: [])

    def fake_config_logging(verbosity):
        captured["verbosity"] = verbosity

    monkeypatch.setattr(deletion_policy_tool, "_config_logging", fake_config_logging)

    result = click.testing.CliRunner().invoke(
        deletion_policy_tool._main,
        args=args,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert captured["verbosity"] == expected_verbosity


def test___verbosity_flags___main___rejects_mixed_verbose_and_quiet(monkeypatch):
    monkeypatch.setattr(deletion_policy_tool, "_load_config", lambda: [])

    result = click.testing.CliRunner().invoke(
        deletion_policy_tool._main,
        args=["-v", "-q"],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert "Cannot use both --verbose and --quiet options together." in result.output


def _assert_result(example_folder, snapshot, files_before):
    snapshot.assert_match(
        "\n".join(remaining_relative_paths(example_folder)) + "\n",
        "expected_remaining_files.txt",
    )
    snapshot.assert_match(
        "\n".join(difflib.ndiff(files_before, remaining_relative_paths(example_folder))) + "\n",
        "diff.txt",
    )


def test___policy_with_extension___main___deletes_expected_files(
    example_folder, snapshot, tmp_path
):
    policies = [
        {
            "folder": str(example_folder),
            "age": 1,
            "extension": ".txt",
        }
    ]
    files_before = remaining_relative_paths(example_folder)

    run_main_cli(tmp_path, policies)

    _assert_result(example_folder, snapshot, files_before)


def test___policy_with_backup_destination___main___delets_only_files_that_have_backups(
    example_folder, snapshot, tmp_path
):
    backup_folder = example_folder.parent / "backup"
    policies = [
        {
            "folder": str(example_folder),
            "age": 1,
            "extension": ".txt",
            "delete_if_backed_up_to": str(backup_folder),
        }
    ]
    files_before = remaining_relative_paths(example_folder)

    run_main_cli(tmp_path, policies)

    _assert_result(example_folder, snapshot, files_before)


def test___policy_with_min_age___main___deletes_only_files_that_are_old_enough(
    example_folder, snapshot, tmp_path
):
    policies = [
        {
            "folder": str(example_folder),
            "age": 5,
            "extension": ".txt",
        }
    ]
    files_before = remaining_relative_paths(example_folder)

    run_main_cli(tmp_path, policies)

    _assert_result(example_folder, snapshot, files_before)


def test___policy_with_copy_to_rule___main___deletes_only_files_that_have_expected_copies(
    example_folder, snapshot, tmp_path
):
    policies = [
        {
            "folder": str(example_folder),
            "age": 1,
            "extension": ".txt",
            "delete_if_copy_exists": [".txt", ".new_suffix"],
        }
    ]
    files_before = remaining_relative_paths(example_folder)

    run_main_cli(tmp_path, policies)

    _assert_result(example_folder, snapshot, files_before)


def test___policy_skips_symlinks___main___leaves_them_in_place(tmp_path):
    folder = tmp_path / "example"
    folder.mkdir()

    external_target = tmp_path / "external_target.txt"
    external_target.write_text("target content")
    os.utime(external_target, (time.time() - (2 * 24 * 60 * 60),) * 2)

    actual_file = folder / "real.txt"
    actual_file.write_text("actual content")
    os.utime(actual_file, (time.time() - (2 * 24 * 60 * 60),) * 2)

    symlink = folder / "link.txt"
    symlink.symlink_to(external_target)

    policies = [{"folder": str(folder), "age": 1, "extension": ".txt"}]

    run_main_cli(tmp_path, policies)

    assert symlink.is_symlink()
    assert symlink.exists()
    assert not actual_file.exists()


def test___multiple_policies___main___retains_expected_files(example_folder, snapshot, tmp_path):
    policies = [
        {
            # delete .new_suffix files if a .txt file exists
            "folder": str(example_folder),
            "age": 1,
            "extension": ".new_suffix",
            "delete_if_copy_exists": [".new_suffix", ".txt"],
        },
        {
            # also delete the .txt file if it was backed up to the backup folder
            "folder": str(example_folder),
            "age": 1,
            "extension": ".txt",
            "delete_if_backed_up_to": str(example_folder.parent / "backup"),
        },
    ]
    files_before = remaining_relative_paths(example_folder)

    run_main_cli(tmp_path, policies)

    _assert_result(example_folder, snapshot, files_before)


def test___multiple_policies_with_remove_folders___main___removes_empty_folders(
    example_folder, snapshot, tmp_path
):
    policies = [
        {  # delete .new_suffix files if a .txt file exists
            "folder": str(example_folder),
            "age": 1,
            "extension": ".new_suffix",
            "delete_if_copy_exists": [".new_suffix", ".txt"],
        },
        {
            # also delete the .txt file if it was backed up to the backup folder
            "folder": str(example_folder),
            "age": 1,
            "extension": ".txt",
            "delete_if_backed_up_to": str(example_folder.parent / "backup"),
        },
    ]
    files_before = remaining_relative_paths(example_folder)

    run_main_cli(tmp_path, policies, args=["--remove-empty-folders"])

    _assert_result(example_folder, snapshot, files_before)


def test___dry_run___main___does_not_delete_files_or_empty_folders(tmp_path):
    folder = tmp_path / "example"
    folder.mkdir()
    empty_folder = folder / "empty"
    empty_folder.mkdir()

    old_file = folder / "old.txt"
    old_file.write_text("content")
    os.utime(old_file, (time.time() - (2 * 24 * 60 * 60),) * 2)

    policies = [{"folder": str(folder), "age": 1, "extension": ".txt"}]
    config_file = tmp_path / "deletion_policy.yml"
    config_file.write_text(yaml.safe_dump(policies), encoding="utf-8")

    result = click.testing.CliRunner().invoke(
        deletion_policy_tool._main,
        env={"DELETION_POLICY_CONFIG_FILE": str(config_file)},
        catch_exceptions=False,
        args=["--dry-run", "--remove-empty-folders"],
        input="",
    )

    assert result.exit_code == 0
    assert old_file.exists()
    assert empty_folder.exists()
    assert "would delete" in result.output.lower()
    assert "would remove empty folder" in result.output.lower()


def test___confirm_each_delete___main___skip_file_when_user_declines(tmp_path):
    folder = tmp_path / "example"
    folder.mkdir()
    old_file = folder / "old.txt"
    old_file.write_text("content")
    os.utime(old_file, (time.time() - (2 * 24 * 60 * 60),) * 2)

    policies = [{"folder": str(folder), "age": 1, "extension": ".txt"}]
    config_file = tmp_path / "deletion_policy.yml"
    config_file.write_text(yaml.safe_dump(policies), encoding="utf-8")

    result = click.testing.CliRunner().invoke(
        deletion_policy_tool._main,
        env={"DELETION_POLICY_CONFIG_FILE": str(config_file)},
        catch_exceptions=False,
        args=["--confirm-each-delete"],
        input="n\n",
    )

    assert result.exit_code == 0
    assert old_file.exists()
    assert "Delete" in result.output or "delete" in result.output.lower()
