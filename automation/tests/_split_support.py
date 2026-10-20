"""Source paths used by tests that inspect the test suite itself."""

from pathlib import Path


def source_files(package: Path) -> tuple[Path, ...]:
    """Read the whole package, and fail rather than scanning an empty directory."""
    paths = tuple(sorted(package.rglob("*.py")))
    assert package.is_dir() and any(path.name.startswith("test_") for path in paths), (
        f"No test sources found in {package}"
    )
    return paths


def read_test_package(package: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in source_files(package))


def all_test_sources(tests: Path) -> tuple[Path, ...]:
    """Include singleton test files and every Python source in each split tier."""
    paths = list(tests.glob("test_tier*.py"))
    for tier in (1, 3, 5):
        paths.extend(path for path in source_files(tests / f"tier{tier}")
                     if path.name.startswith("test_"))
    return tuple(sorted(paths))


def report_key(path: Path) -> str:
    """Report rows aggregate a split package, or one unsplit tier file."""
    if path.parent.name in {"tier1", "tier3", "tier5"}:
        return f"{path.parent.name}/"
    return path.name
