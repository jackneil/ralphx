"""Import manager for RalphX.

Handles importing content into loops:
- Markdown files → copied to loop inputs directory
- JSONL files → parsed into database work items
- Paste → create new file in inputs directory

Input files can have tags (master_design, story_instructions, etc.)
for validation and organization purposes.
"""

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from ralphx.core.workspace import (
    ensure_loop_directory,
    get_loop_inputs_path,
)

# Metadata filename for storing input tags
INPUTS_METADATA_FILE = ".inputs_metadata.json"


class ImportError(Exception):
    """Import operation failed."""

    pass


class ImportResult:
    """Result of an import operation."""

    def __init__(
        self,
        success: bool = True,
        files_imported: int = 0,
        items_created: int = 0,
        errors: list[str] = None,
        paths: list[Path] = None,
    ):
        self.success = success
        self.files_imported = files_imported
        self.items_created = items_created
        self.errors = errors or []
        self.paths = paths or []

    def __repr__(self) -> str:
        return (
            f"ImportResult(success={self.success}, files={self.files_imported}, "
            f"items={self.items_created}, errors={len(self.errors)})"
        )


class ImportManager:
    """Manages importing content into loops.

    Supports:
    - Markdown files: copied to <project>/.ralphx/loops/<loop>/inputs/
    - JSONL files: parsed and items created in project database
    - Paste content: saved as new file in inputs directory

    Input files can have tags stored in a metadata file for validation.
    """

    def __init__(self, project_path: Path, project_db=None):
        """Initialize the import manager.

        Args:
            project_path: Path to the project directory.
            project_db: Optional ProjectDatabase instance for creating items.
        """
        self.project_path = Path(project_path)
        self.project_db = project_db

    def _get_metadata_path(self, loop_name: str) -> Path:
        """Get path to the inputs metadata file."""
        inputs_dir = get_loop_inputs_path(self.project_path, loop_name)
        return inputs_dir / INPUTS_METADATA_FILE

    def _load_metadata(self, loop_name: str) -> dict:
        """Load input metadata from file.

        Returns:
            Dict mapping filename to metadata (tag, applied_from_template, etc.)
        """
        metadata_path = self._get_metadata_path(loop_name)
        if metadata_path.exists():
            try:
                return json.loads(metadata_path.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_metadata(self, loop_name: str, metadata: dict) -> bool:
        """Save input metadata to file.

        Returns:
            True if saved successfully.
        """
        metadata_path = self._get_metadata_path(loop_name)
        try:
            metadata_path.write_text(json.dumps(metadata, indent=2))
            return True
        except OSError:
            return False

    def _set_file_metadata(
        self,
        loop_name: str,
        filename: str,
        tag: Optional[str] = None,
        applied_from_template: Optional[str] = None,
    ) -> bool:
        """Set metadata for a specific input file.

        Args:
            loop_name: Name of the loop.
            filename: Input filename.
            tag: Optional tag for the input.
            applied_from_template: Optional template ID if from template.

        Returns:
            True if saved successfully.
        """
        metadata = self._load_metadata(loop_name)
        file_meta = metadata.get(filename, {})

        if tag is not None:
            file_meta["tag"] = tag
        if applied_from_template is not None:
            file_meta["applied_from_template"] = applied_from_template

        if file_meta:
            metadata[filename] = file_meta
        elif filename in metadata:
            del metadata[filename]

        return self._save_metadata(loop_name, metadata)

    def _get_file_metadata(self, loop_name: str, filename: str) -> dict:
        """Get metadata for a specific input file.

        Returns:
            Dict with tag, applied_from_template, etc. or empty dict.
        """
        metadata = self._load_metadata(loop_name)
        return metadata.get(filename, {})

    def import_markdown(
        self,
        source_path: Path,
        loop_name: str,
        rename: Optional[str] = None,
    ) -> ImportResult:
        """Import a markdown file into a loop's inputs directory.

        Args:
            source_path: Path to the markdown file to import.
            loop_name: Name of the target loop.
            rename: Optional new name for the file.

        Returns:
            ImportResult with import status.
        """
        source_path = Path(source_path)

        if not source_path.exists():
            return ImportResult(
                success=False,
                errors=[f"File not found: {source_path}"],
            )

        if not source_path.is_file():
            return ImportResult(
                success=False,
                errors=[f"Not a file: {source_path}"],
            )

        # Ensure loop directory exists
        ensure_loop_directory(self.project_path, loop_name)
        inputs_dir = get_loop_inputs_path(self.project_path, loop_name)

        # Determine destination filename - sanitize to prevent path traversal
        dest_name = rename if rename else source_path.name
        # Strip any directory components and path traversal attempts
        dest_name = Path(dest_name).name  # Gets just the filename, strips ../
        # Extra safety: remove any remaining path separators
        dest_name = dest_name.replace("/", "_").replace("\\", "_")
        if not dest_name.endswith(".md"):
            dest_name += ".md"

        dest_path = inputs_dir / dest_name

        # Security: verify destination is within inputs directory
        try:
            dest_path_resolved = dest_path.resolve()
            inputs_dir_resolved = inputs_dir.resolve()
            # Use relative_to() for safe path containment check (startswith is vulnerable)
            dest_path_resolved.relative_to(inputs_dir_resolved)
        except ValueError:
            return ImportResult(
                success=False,
                errors=["Invalid filename: path traversal detected"],
            )
        except Exception:
            return ImportResult(
                success=False,
                errors=["Invalid filename"],
            )

        # Copy file
        try:
            shutil.copy2(source_path, dest_path)
            return ImportResult(
                success=True,
                files_imported=1,
                paths=[dest_path],
            )
        except Exception as e:
            return ImportResult(
                success=False,
                errors=[f"Failed to copy file: {e}"],
            )

    def import_markdown_glob(
        self,
        pattern: str,
        loop_name: str,
        base_path: Optional[Path] = None,
    ) -> ImportResult:
        """Import multiple markdown files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "docs/*.md").
            loop_name: Name of the target loop.
            base_path: Base path for glob (defaults to project path).

        Returns:
            ImportResult with combined results.
        """
        base = Path(base_path) if base_path else self.project_path
        files = list(base.glob(pattern))

        if not files:
            return ImportResult(
                success=True,
                files_imported=0,
                errors=["No files matched pattern"],
            )

        all_paths = []
        all_errors = []

        for file_path in files:
            if file_path.is_file():
                result = self.import_markdown(file_path, loop_name)
                if result.success:
                    all_paths.extend(result.paths)
                else:
                    all_errors.extend(result.errors)

        return ImportResult(
            success=len(all_errors) == 0,
            files_imported=len(all_paths),
            paths=all_paths,
            errors=all_errors,
        )

    def import_jsonl(
        self,
        source_path: Path,
        loop_name: str,
        project_id: str,
    ) -> ImportResult:
        """Import a JSONL file as work items.

        Each line should be a JSON object with at least:
        - id: Item identifier
        - content: Item content

        Optional fields:
        - priority: int (1-5)
        - category: str
        - tags: list[str]
        - metadata: dict

        Args:
            source_path: Path to the JSONL file.
            loop_name: Name of the loop these items belong to.
            project_id: Project ID for database insertion.

        Returns:
            ImportResult with import status.
        """
        if not self.project_db:
            return ImportResult(
                success=False,
                errors=["No project database configured - cannot import items"],
            )

        source_path = Path(source_path)

        if not source_path.exists():
            return ImportResult(
                success=False,
                errors=[f"File not found: {source_path}"],
            )

        items_created = 0
        errors = []

        try:
            with open(source_path, "r") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        item = json.loads(line)

                        # Validate required fields
                        if "id" not in item:
                            item["id"] = f"ITEM-{uuid.uuid4().hex[:8]}"

                        if "content" not in item:
                            errors.append(f"Line {line_num}: missing 'content' field")
                            continue

                        # Create work item
                        self.project_db.create_work_item(
                            id=str(item["id"]),
                            project_id=project_id,
                            content=item["content"],
                            title=item.get("title"),
                            priority=item.get("priority"),
                            status="completed",  # Items ready for consumption
                            category=item.get("category"),
                            tags=item.get("tags"),
                            metadata=item.get("metadata"),
                            source_loop=loop_name,
                            item_type=item.get("item_type", "story"),
                        )
                        items_created += 1

                    except json.JSONDecodeError as e:
                        errors.append(f"Line {line_num}: invalid JSON - {e}")
                    except Exception as e:
                        errors.append(f"Line {line_num}: failed to create item - {e}")

        except Exception as e:
            return ImportResult(
                success=False,
                errors=[f"Failed to read file: {e}"],
            )

        # Also copy JSONL to inputs for reference
        ensure_loop_directory(self.project_path, loop_name)
        inputs_dir = get_loop_inputs_path(self.project_path, loop_name)
        # Sanitize filename to prevent path traversal (defense in depth)
        safe_name = Path(source_path.name).name.replace("/", "_").replace("\\", "_")
        dest_path = inputs_dir / safe_name

        try:
            # Verify destination is within inputs directory using relative_to (safe)
            dest_path_resolved = dest_path.resolve()
            inputs_dir_resolved = inputs_dir.resolve()
            dest_path_resolved.relative_to(inputs_dir_resolved)  # Raises ValueError if not contained
            shutil.copy2(source_path, dest_path)
        except (ValueError, Exception):
            pass  # Not critical if copy fails or path is invalid

        return ImportResult(
            success=len(errors) == 0 or items_created > 0,
            items_created=items_created,
            files_imported=1 if items_created > 0 else 0,
            paths=[dest_path] if dest_path.exists() else [],
            errors=errors,
        )

    def import_paste(
        self,
        content: str,
        loop_name: str,
        filename: str,
        tag: Optional[str] = None,
        applied_from_template: Optional[str] = None,
    ) -> ImportResult:
        """Import pasted content as a new file.

        Args:
            content: The content to save.
            loop_name: Name of the target loop.
            filename: Name for the new file.
            tag: Optional tag for the input (master_design, story_instructions, etc.)
            applied_from_template: Optional template ID if content is from a template.

        Returns:
            ImportResult with import status.
        """
        if not content.strip():
            return ImportResult(
                success=False,
                errors=["Content is empty"],
            )

        # Ensure loop directory exists
        ensure_loop_directory(self.project_path, loop_name)
        inputs_dir = get_loop_inputs_path(self.project_path, loop_name)

        # Sanitize filename
        safe_filename = "".join(
            c for c in filename if c.isalnum() or c in "._-"
        )
        if not safe_filename:
            safe_filename = f"paste-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        if not safe_filename.endswith((".md", ".txt", ".jsonl")):
            safe_filename += ".md"

        dest_path = inputs_dir / safe_filename

        # Handle duplicate names
        counter = 1
        original_stem = Path(safe_filename).stem
        original_suffix = Path(safe_filename).suffix
        while dest_path.exists():
            dest_path = inputs_dir / f"{original_stem}-{counter}{original_suffix}"
            counter += 1

        try:
            dest_path.write_text(content)

            # Save metadata if tag or template provided
            if tag or applied_from_template:
                self._set_file_metadata(
                    loop_name,
                    dest_path.name,
                    tag=tag,
                    applied_from_template=applied_from_template,
                )

            return ImportResult(
                success=True,
                files_imported=1,
                paths=[dest_path],
            )
        except Exception as e:
            return ImportResult(
                success=False,
                errors=[f"Failed to write file: {e}"],
            )

    def list_inputs(self, loop_name: str) -> list[dict]:
        """List all input files for a loop.

        Args:
            loop_name: Name of the loop.

        Returns:
            List of dicts with file info (name, path, size, modified, tag).
        """
        inputs_dir = get_loop_inputs_path(self.project_path, loop_name)

        if not inputs_dir.exists():
            return []

        # Load metadata for tags
        metadata = self._load_metadata(loop_name)

        files = []
        for file_path in sorted(inputs_dir.iterdir()):
            if file_path.is_file() and not file_path.name.startswith("."):
                stat = file_path.stat()
                file_meta = metadata.get(file_path.name, {})
                files.append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "tag": file_meta.get("tag"),
                })

        return files

    def delete_input(self, loop_name: str, filename: str) -> bool:
        """Delete an input file.

        Args:
            loop_name: Name of the loop.
            filename: Name of the file to delete.

        Returns:
            True if deleted, False if not found.
        """
        inputs_dir = get_loop_inputs_path(self.project_path, loop_name)
        file_path = inputs_dir / filename

        # Security: ensure file is within inputs directory using relative_to (safe)
        try:
            file_path = file_path.resolve()
            inputs_dir_resolved = inputs_dir.resolve()
            file_path.relative_to(inputs_dir_resolved)  # Raises ValueError if not contained
        except (ValueError, Exception):
            return False

        if file_path.exists() and file_path.is_file():
            file_path.unlink()
            # Also remove metadata for this file
            metadata = self._load_metadata(loop_name)
            if filename in metadata:
                del metadata[filename]
                self._save_metadata(loop_name, metadata)
            return True

        return False

    def update_input_tag(
        self, loop_name: str, filename: str, tag: Optional[str]
    ) -> bool:
        """Update the tag of an input file.

        Args:
            loop_name: Name of the loop.
            filename: Name of the file.
            tag: New tag (or None to remove tag).

        Returns:
            True if updated successfully.
        """
        # Verify file exists first
        inputs_dir = get_loop_inputs_path(self.project_path, loop_name)
        file_path = inputs_dir / filename

        if not file_path.exists() or not file_path.is_file():
            return False

        return self._set_file_metadata(loop_name, filename, tag=tag)

    def get_input_content(self, loop_name: str, filename: str) -> Optional[str]:
        """Get the content of an input file.

        Args:
            loop_name: Name of the loop.
            filename: Name of the file.

        Returns:
            File content or None if not found.
        """
        inputs_dir = get_loop_inputs_path(self.project_path, loop_name)
        file_path = inputs_dir / filename

        # Security: ensure file is within inputs directory using relative_to (safe)
        try:
            file_path = file_path.resolve()
            inputs_dir_resolved = inputs_dir.resolve()
            file_path.relative_to(inputs_dir_resolved)  # Raises ValueError if not contained
        except (ValueError, Exception):
            return None

        if file_path.exists() and file_path.is_file():
            try:
                return file_path.read_text()
            except Exception:
                return None

        return None
