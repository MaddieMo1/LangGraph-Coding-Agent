import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath


SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_MANIFEST_NAME = "unity-snapshot.json"
ALLOWED_ROOTS = ("Assets", "Packages", "ProjectSettings")
MANAGED_PREFIXES = (
    "Assets/Generated",
    "Assets/Tests/EditMode",
    "Assets/Tests/PlayMode",
)
DEFAULT_MAX_FILES = 50000
DEFAULT_MAX_FILE_SIZE = 128 * 1024 * 1024
DEFAULT_MAX_TOTAL_SIZE = 4 * 1024 * 1024 * 1024
_UNITY_VERSION_PATTERN = re.compile(r"^m_EditorVersion:\s*(?P<version>\S+)\s*$", re.M)


class UnitySnapshotError(ValueError):
    pass


class UnitySnapshotBuilder:
    def __init__(
        self,
        project_path,
        production_source_path,
        editmode_test_source_path,
        playmode_test_source_path,
        max_files=DEFAULT_MAX_FILES,
        max_file_size=DEFAULT_MAX_FILE_SIZE,
        max_total_size=DEFAULT_MAX_TOTAL_SIZE,
    ):
        self.project_path = Path(project_path).resolve()
        self.production_source_path = Path(production_source_path).resolve()
        self.editmode_test_source_path = Path(editmode_test_source_path).resolve()
        self.playmode_test_source_path = Path(playmode_test_source_path).resolve()
        self.max_files = max_files
        self.max_file_size = max_file_size
        self.max_total_size = max_total_size

    def build(self, archive_path):
        archive_path = Path(archive_path).resolve()
        self._validate_environment()
        source_before = self._project_fingerprint()
        sources = self._snapshot_sources()
        files = self._file_manifest(sources)
        package_path = "Packages/manifest.json"
        package_entry = next(
            (item for item in files if item["path"] == package_path), None
        )
        if package_entry is None:
            raise UnitySnapshotError("Unity project is missing Packages/manifest.json")

        manifest_content = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "unity_version": self._unity_version(sources),
            "package_manifest_sha256": package_entry["sha256"],
            "files": files,
        }
        manifest = {
            **manifest_content,
            "snapshot_sha256": _canonical_digest(manifest_content),
        }

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = archive_path.with_name(
            f".{archive_path.name}.tmp-{uuid.uuid4().hex}"
        )
        try:
            self._write_archive(temporary_path, manifest, sources)
            source_after = self._project_fingerprint()
            if source_before != source_after:
                raise UnitySnapshotError("Unity source project changed during snapshot")
            archive_sha256 = _file_digest(temporary_path)
            os.replace(temporary_path, archive_path)
        except Exception:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        return {
            **manifest,
            "archive_sha256": archive_sha256,
            "archive_path": str(archive_path),
            "source_fingerprint_before": source_before,
            "source_fingerprint_after": source_after,
            "source_unchanged": source_before == source_after,
        }

    def _validate_environment(self):
        for root in ALLOWED_ROOTS:
            path = self.project_path / root
            if not path.is_dir():
                raise UnitySnapshotError(
                    f"invalid Unity project, missing {root}: {self.project_path}"
                )
        for label, path in (
            ("production", self.production_source_path),
            ("EditMode", self.editmode_test_source_path),
            ("PlayMode", self.playmode_test_source_path),
        ):
            if not path.is_dir() or not any(
                item.is_file() and item.suffix == ".cs" for item in path.iterdir()
            ):
                raise UnitySnapshotError(f"no {label} C# files: {path}")
        if not isinstance(self.max_files, int) or self.max_files < 1:
            raise UnitySnapshotError("max_files must be a positive integer")
        if not isinstance(self.max_file_size, int) or self.max_file_size < 1:
            raise UnitySnapshotError("max_file_size must be a positive integer")
        if not isinstance(self.max_total_size, int) or self.max_total_size < 1:
            raise UnitySnapshotError("max_total_size must be a positive integer")

    def _project_fingerprint(self):
        entries = []
        for root in ALLOWED_ROOTS:
            root_path = self.project_path / root
            for path in sorted(root_path.rglob("*"), key=lambda item: item.as_posix()):
                if path.is_symlink():
                    raise UnitySnapshotError(
                        f"symbolic link is not allowed in Unity source: {path.name}"
                    )
                if path.is_file():
                    relative = path.relative_to(self.project_path).as_posix()
                    entries.append(
                        {
                            "path": relative,
                            "size": path.stat().st_size,
                            "sha256": _file_digest(path),
                        }
                    )
        return _canonical_digest(entries)

    def _snapshot_sources(self):
        sources = {}
        for root in ALLOWED_ROOTS:
            root_path = self.project_path / root
            for path in sorted(root_path.rglob("*"), key=lambda item: item.as_posix()):
                if path.is_symlink():
                    raise UnitySnapshotError(
                        f"symbolic link is not allowed in Unity source: {path.name}"
                    )
                if not path.is_file():
                    continue
                relative = path.relative_to(self.project_path).as_posix()
                if _is_managed_path(relative):
                    continue
                sources[relative] = path

        self._add_generated_sources(
            sources,
            self.production_source_path,
            "Assets/Generated",
        )
        self._add_generated_sources(
            sources,
            self.editmode_test_source_path,
            "Assets/Tests/EditMode",
        )
        self._add_generated_sources(
            sources,
            self.playmode_test_source_path,
            "Assets/Tests/PlayMode",
        )
        return dict(sorted(sources.items()))

    @staticmethod
    def _add_generated_sources(sources, source_root, target_root):
        for path in sorted(source_root.iterdir(), key=lambda item: item.name):
            if path.is_symlink():
                raise UnitySnapshotError(
                    f"symbolic link is not allowed in generated sources: {path.name}"
                )
            if path.is_dir():
                raise UnitySnapshotError(
                    f"nested generated source directory is not allowed: {path.name}"
                )
            if path.is_file() and path.suffix == ".cs":
                sources[f"{target_root}/{path.name}"] = path

    def _file_manifest(self, sources):
        if not sources:
            raise UnitySnapshotError("snapshot contains no files")
        if len(sources) > self.max_files:
            raise UnitySnapshotError("snapshot exceeds maximum file count")
        total_size = 0
        files = []
        for relative, source in sorted(sources.items()):
            size = source.stat().st_size
            if size > self.max_file_size:
                raise UnitySnapshotError(f"file exceeds maximum size: {relative}")
            total_size += size
            if total_size > self.max_total_size:
                raise UnitySnapshotError("snapshot exceeds maximum total size")
            files.append(
                {"path": relative, "size": size, "sha256": _file_digest(source)}
            )
        return files

    @staticmethod
    def _unity_version(sources):
        version_path = "ProjectSettings/ProjectVersion.txt"
        source = sources.get(version_path)
        if source is None:
            raise UnitySnapshotError("Unity project is missing ProjectVersion.txt")
        try:
            content = source.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            raise UnitySnapshotError(str(error)) from error
        match = _UNITY_VERSION_PATTERN.search(content)
        if not match:
            raise UnitySnapshotError("ProjectVersion.txt has no Unity editor version")
        return match.group("version")

    def _write_archive(self, path, manifest, sources):
        expected = {item["path"]: item for item in manifest["files"]}
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            _write_deterministic_entry(
                archive,
                SNAPSHOT_MANIFEST_NAME,
                _canonical_json(manifest) + b"\n",
            )
            for relative, source in sorted(sources.items()):
                _write_deterministic_file(
                    archive,
                    relative,
                    source,
                    expected[relative],
                )


def safe_extract_snapshot(
    archive_path,
    destination,
    max_files=DEFAULT_MAX_FILES,
    max_file_size=DEFAULT_MAX_FILE_SIZE,
    max_total_size=DEFAULT_MAX_TOTAL_SIZE,
):
    archive_path = Path(archive_path).resolve()
    destination = Path(destination).resolve()
    if destination.exists():
        raise UnitySnapshotError(f"snapshot destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".unity-snapshot-", dir=destination.parent))
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)):
                raise UnitySnapshotError("snapshot archive contains duplicate paths")
            if SNAPSHOT_MANIFEST_NAME not in names:
                raise UnitySnapshotError("snapshot archive has no manifest")
            if len(entries) - 1 > max_files:
                raise UnitySnapshotError("snapshot exceeds maximum file count")
            total_size = 0
            for entry in entries:
                _validate_archive_entry(entry, max_file_size)
                if entry.filename != SNAPSHOT_MANIFEST_NAME:
                    total_size += entry.file_size
                    if total_size > max_total_size:
                        raise UnitySnapshotError("snapshot exceeds maximum total size")

            try:
                manifest = json.loads(archive.read(SNAPSHOT_MANIFEST_NAME))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise UnitySnapshotError(f"invalid snapshot manifest: {error}") from error
            _validate_snapshot_manifest(manifest)
            expected = {item["path"]: item for item in manifest["files"]}
            actual = set(names) - {SNAPSHOT_MANIFEST_NAME}
            if actual != set(expected):
                raise UnitySnapshotError("snapshot archive files do not match manifest")

            for relative in sorted(expected):
                target = staging.joinpath(*PurePosixPath(relative).parts)
                resolved = target.resolve()
                if staging != resolved and staging not in resolved.parents:
                    raise UnitySnapshotError(f"unsafe snapshot path: {relative}")
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                with archive.open(relative, "r") as source, target.open("wb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > max_file_size:
                            raise UnitySnapshotError(f"file exceeds maximum size: {relative}")
                        digest.update(chunk)
                        output.write(chunk)
                if size != expected[relative]["size"]:
                    raise UnitySnapshotError(f"snapshot size mismatch: {relative}")
                if digest.hexdigest() != expected[relative]["sha256"]:
                    raise UnitySnapshotError(f"snapshot hash mismatch: {relative}")
        os.replace(staging, destination)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _validate_snapshot_manifest(manifest):
    required = {
        "schema_version",
        "snapshot_sha256",
        "unity_version",
        "package_manifest_sha256",
        "files",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise UnitySnapshotError("snapshot manifest fields are invalid")
    if manifest.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise UnitySnapshotError("unsupported snapshot schema version")
    if not isinstance(manifest.get("files"), list) or not manifest["files"]:
        raise UnitySnapshotError("snapshot manifest files are invalid")
    paths = []
    for item in manifest["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise UnitySnapshotError("snapshot file manifest is invalid")
        if not _safe_snapshot_path(item["path"]):
            raise UnitySnapshotError(f"unsafe snapshot path: {item['path']}")
        if not isinstance(item["size"], int) or item["size"] < 0:
            raise UnitySnapshotError("snapshot file size is invalid")
        if not _is_digest(item["sha256"]):
            raise UnitySnapshotError("snapshot file digest is invalid")
        paths.append(item["path"])
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise UnitySnapshotError("snapshot manifest paths are not unique and sorted")
    package = next(
        (item for item in manifest["files"] if item["path"] == "Packages/manifest.json"),
        None,
    )
    if package is None or package["sha256"] != manifest.get("package_manifest_sha256"):
        raise UnitySnapshotError("package manifest digest does not match snapshot")
    content = {
        "schema_version": manifest["schema_version"],
        "unity_version": manifest["unity_version"],
        "package_manifest_sha256": manifest["package_manifest_sha256"],
        "files": manifest["files"],
    }
    if manifest.get("snapshot_sha256") != _canonical_digest(content):
        raise UnitySnapshotError("snapshot manifest digest does not match content")


def _validate_archive_entry(entry, max_file_size):
    name = entry.filename
    mode = entry.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise UnitySnapshotError(f"symbolic link is not allowed: {name}")
    if name == SNAPSHOT_MANIFEST_NAME:
        if entry.file_size > 1024 * 1024:
            raise UnitySnapshotError("snapshot manifest is too large")
        return
    if not _safe_snapshot_path(name):
        raise UnitySnapshotError(f"unsafe snapshot path: {name}")
    if entry.is_dir():
        raise UnitySnapshotError(f"directory entries are not allowed: {name}")
    if entry.file_size > max_file_size:
        raise UnitySnapshotError(f"file exceeds maximum size: {name}")


def _safe_snapshot_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
        and path.parts[0] in ALLOWED_ROOTS
    )


def _is_managed_path(relative):
    return any(
        relative == prefix or relative.startswith(prefix + "/")
        for prefix in MANAGED_PREFIXES
    )


def _write_deterministic_entry(archive, name, content):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, content)


def _write_deterministic_file(archive, name, source_path, expected):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    digest = hashlib.sha256()
    size = 0
    with Path(source_path).open("rb") as source, archive.open(info, "w") as output:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
            output.write(chunk)
    if size != expected["size"] or digest.hexdigest() != expected["sha256"]:
        raise UnitySnapshotError(f"snapshot source changed during build: {name}")


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_digest(value):
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _is_digest(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
