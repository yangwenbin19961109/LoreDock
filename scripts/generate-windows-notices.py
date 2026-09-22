"""Collect installed dependency notices for the Windows desktop bundle.

The output is intentionally conservative: build-only packages may be listed, but
missing license texts are reported rather than silently treated as complete.
"""

from __future__ import annotations

import importlib.metadata
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "apps/desktop/src-tauri/Cargo.toml"
OUTPUT = ROOT / "apps/desktop/src-tauri/target/loredock-third-party-notices"
SUPPLEMENT = ROOT / "licenses/upstream"
LICENSE_NAME = re.compile(r"^(?:LICEN[CS]E|COPYING|NOTICE)(?:[._-]|$)", re.IGNORECASE)
TREE_PACKAGE = re.compile(r"^(\S+) v(\S+)")


def command_json(args: list[str]) -> Any:
    result = subprocess.run(
        args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=True
    )
    return json.loads(result.stdout)


def read_notice_files(root: Path, relative_paths: list[Path]) -> list[tuple[str, str]]:
    notices: list[tuple[str, str]] = []
    resolved_root = root.resolve()
    for relative in sorted(set(relative_paths), key=str):
        path = (root / relative).resolve()
        if not path.is_relative_to(resolved_root) or not path.is_file():
            continue
        if path.stat().st_size > 1_000_000:
            continue
        notices.append(
            (relative.as_posix(), path.read_text(encoding="utf-8", errors="replace"))
        )
    return notices


def read_supplement_notices(
    ecosystem: str, name: str, version: str
) -> list[tuple[str, str]]:
    """Read notice texts collected from upstream when a package ships none locally.

    Files live under ``licenses/upstream/{ecosystem}/{name}/{version}/`` and are
    committed to the repository so the bundle output is reproducible on any host.
    """
    directory = SUPPLEMENT / ecosystem / name / version
    if not directory.is_dir():
        return []
    notices: list[tuple[str, str]] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        notices.append(
            (
                f"upstream/{path.name}",
                path.read_text(encoding="utf-8", errors="replace"),
            )
        )
    return notices


def with_supplement(
    notices: list[tuple[str, str]], ecosystem: str, name: str, version: str
) -> list[tuple[str, str]]:
    if notices:
        return notices
    return read_supplement_notices(ecosystem, name, version)


def cargo_notices() -> tuple[list[str], list[str]]:
    metadata = command_json(
        [
            "cargo",
            "metadata",
            "--manifest-path",
            str(MANIFEST),
            "--format-version",
            "1",
            "--locked",
        ]
    )
    tree = subprocess.run(
        [
            "cargo",
            "tree",
            "--manifest-path",
            str(MANIFEST),
            "--target",
            "x86_64-pc-windows-msvc",
            "--edges",
            "normal",
            "--prefix",
            "none",
            "--locked",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    ).stdout
    included = {
        match.groups()
        for line in tree.splitlines()
        if (match := TREE_PACKAGE.match(line))
    }
    sections: list[str] = []
    missing: list[str] = []
    for package in sorted(
        metadata["packages"], key=lambda item: (item["name"], item["version"])
    ):
        name, version = package["name"], package["version"]
        if (name, version) not in included or not str(
            package.get("source", "")
        ).startswith("registry+"):
            continue
        root = Path(package["manifest_path"]).parent
        paths = [
            path.relative_to(root)
            for path in root.iterdir()
            if path.is_file() and LICENSE_NAME.match(path.name)
        ]
        for directory_name in ("LICENSES", "licenses"):
            directory = root / directory_name
            if directory.is_dir():
                paths.extend(
                    path.relative_to(root)
                    for path in directory.iterdir()
                    if path.is_file()
                )
        license_file = package.get("license_file")
        if license_file:
            paths.append(Path(license_file))
        notices = with_supplement(read_notice_files(root, paths), "rust", name, version)
        source = (
            package.get("repository") or f"https://crates.io/crates/{name}/{version}"
        )
        sections.append(
            format_section(
                "Rust", name, version, package.get("license"), source, notices
            )
        )
        if not notices:
            missing.append(f"Rust {name} {version}: no local license or notice text")
    return sections, missing


def python_notices() -> tuple[list[str], list[str]]:
    sections: list[str] = []
    missing: list[str] = []
    for distribution in sorted(
        importlib.metadata.distributions(),
        key=lambda item: item.metadata.get("Name", "").lower(),
    ):
        name = distribution.metadata.get("Name", "")
        if not name or name == "loredock-core":
            continue
        paths = [
            Path(str(path))
            for path in distribution.files or []
            if LICENSE_NAME.match(path.name)
        ]
        notices: list[tuple[str, str]] = []
        for relative in sorted(paths, key=str):
            path = Path(distribution.locate_file(relative))
            if path.is_file() and path.stat().st_size <= 1_000_000:
                notices.append(
                    (
                        relative.as_posix(),
                        path.read_text(encoding="utf-8", errors="replace"),
                    )
                )
        metadata = distribution.metadata
        source = (
            metadata.get("Home-page")
            or f"https://pypi.org/project/{name}/{distribution.version}/"
        )
        license_name = metadata.get("License-Expression") or metadata.get("License")
        notices = with_supplement(notices, "python", name, distribution.version)
        sections.append(
            format_section(
                "Python", name, distribution.version, license_name, source, notices
            )
        )
        if not notices:
            missing.append(
                f"Python {name} {distribution.version}: no installed license or notice text"
            )
    return sections, missing


def web_notices() -> tuple[list[str], list[str]]:
    pnpm = "pnpm.cmd" if sys.platform == "win32" else "pnpm"
    workspace = command_json(
        [
            pnpm,
            "--filter",
            "@loredock/web",
            "ls",
            "--prod",
            "--depth",
            "Infinity",
            "--json",
        ]
    )[0]
    packages: dict[tuple[str, str], dict[str, Any]] = {}

    def visit(dependencies: dict[str, Any]) -> None:
        for name, dependency in dependencies.items():
            version = dependency["version"]
            if not version.startswith("link:"):
                packages[(name, version)] = dependency
            visit(dependency.get("dependencies", {}))

    visit(workspace.get("dependencies", {}))
    sections: list[str] = []
    missing: list[str] = []
    for (name, version), dependency in sorted(packages.items()):
        root = Path(dependency["path"])
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
        paths = [
            path.relative_to(root)
            for path in root.iterdir()
            if path.is_file() and LICENSE_NAME.match(path.name)
        ]
        notices = read_notice_files(root, paths)
        repository = package.get("repository")
        source = repository.get("url") if isinstance(repository, dict) else repository
        sections.append(
            format_section(
                "Web", name, version, package.get("license"), source, notices
            )
        )
        if not notices:
            missing.append(f"Web {name} {version}: no local license or notice text")
    return sections, missing


def format_section(
    ecosystem: str,
    name: str,
    version: str,
    license_name: str | None,
    source: str | None,
    notices: list[tuple[str, str]],
) -> str:
    lines = [
        f"===== {ecosystem}: {name} {version} =====",
        f"License: {license_name or 'not stated in local metadata'}",
        f"Source: {source or 'not stated in local metadata'}",
    ]
    for filename, contents in notices:
        lines.extend((f"----- {filename} -----", contents.rstrip()))
    if not notices:
        lines.append("NOTICE TEXT NOT FOUND IN LOCAL PACKAGE; REVIEW REQUIRED.")
    return "\n".join(lines)


def main() -> None:
    sections: list[str] = []
    missing: list[str] = []
    for collector in (cargo_notices, python_notices, web_notices):
        found, gaps = collector()
        sections.extend(found)
        missing.extend(gaps)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "THIRD_PARTY_NOTICES.txt").write_text(
        "LoreDock Windows dependency notices\n"
        "Generated from the locked local dependency trees at packaging time.\n"
        "This inventory may include build-only packages.\n"
        "See REVIEW_NEEDED.txt for unresolved notice texts.\n\n"
        + "\n\n".join(sections)
        + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "REVIEW_NEEDED.txt").write_text(
        (
            "Unresolved local notice texts; do not treat this bundle as a complete license audit.\n\n"
            + "\n".join(missing)
            + "\n"
        )
        if missing
        else (
            "No unresolved notice texts in this bundle. "
            "Every listed dependency has a local or upstream-supplemented license text.\n"
        ),
        encoding="utf-8",
    )
    print(
        f"Collected {len(sections)} dependency entries; {len(missing)} need notice review."
    )


if __name__ == "__main__":
    main()
