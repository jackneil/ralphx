"""Tests for JSONL import functionality.

Tests the import_jsonl method in ProjectDB for handling hank-rcm style JSONL files
with various statuses (pending, implemented, dup, external, skipped).
"""

import json
import tempfile
from pathlib import Path

import pytest


class TestJsonlImport:
    """Test JSONL import with status mapping."""

    @pytest.fixture
    def project_db(self, tmp_path):
        """Create a temporary ProjectDB for testing."""
        from ralphx.core.project_db import ProjectDatabase

        db = ProjectDatabase(str(tmp_path / "test.db"))
        db.seed_defaults_if_empty()

        # Create a workflow for the items
        db.create_workflow("test-workflow", "Test Workflow", namespace="test")
        db.create_workflow_step(
            workflow_id="test-workflow",
            step_number=1,
            name="Import Step",
            step_type="import",
        )

        return db

    @pytest.fixture
    def sample_jsonl_file(self, tmp_path):
        """Create a sample JSONL file with various statuses."""
        items = [
            # Item with no status (should default to pending -> completed)
            {
                "id": "FND-001",
                "priority": 1,
                "story": "System has Patient model for MPI",
                "acceptance_criteria": ["Criterion 1", "Criterion 2"],
                "passes": False,
                "notes": "Some notes",
            },
            # Item with pending status
            {
                "id": "FND-002",
                "priority": 2,
                "story": "System has PatientInsurance model",
                "acceptance_criteria": ["Criterion 1"],
                "status": "pending",
                "passes": False,
            },
            # Item with implemented status
            {
                "id": "FND-003",
                "priority": 3,
                "story": "System has Encounter model",
                "acceptance_criteria": ["Criterion 1"],
                "status": "implemented",
                "passes": True,
                "impl_notes": "Implemented with full CRUD API",
                "implemented_at": "2026-01-13T16:39:56.439126",
            },
            # Item with dup status
            {
                "id": "ADM-004",
                "priority": 15,
                "story": "As an admin, I can manage code sets",
                "status": "dup",
                "passes": True,
                "dup_of": "ADM-001",
            },
            # Item with external status (long story to test title truncation)
            {
                "id": "CHG-001",
                "priority": 28,
                "story": "As a biller, I can validate anesthesia start and stop times against CMS IOM 100-04 Chapter 12 requirements so that time documentation is accurate",
                "status": "external",
                "passes": False,
                "external_product": "claim_cleaner",
            },
            # Item with skipped status
            {
                "id": "ANS-099",
                "priority": 99,
                "story": "Feature that cannot be implemented",
                "status": "skipped",
                "passes": True,
                "skip_reason": "Requires external API not available",
            },
        ]

        file_path = tmp_path / "test_items.jsonl"
        with open(file_path, "w") as f:
            for item in items:
                f.write(json.dumps(item) + "\n")

        return str(file_path)

    def test_import_pending_only_mode(self, project_db, sample_jsonl_file):
        """Test importing only pending items (pending_only mode)."""
        result = project_db.import_jsonl(
            file_path=sample_jsonl_file,
            format_id="hank_prd",
            workflow_id="test-workflow",
            source_step_id=1,
            import_mode="pending_only",
        )

        # Should import 2 items (FND-001 no status, FND-002 pending)
        # Should skip 4 items (implemented, dup, external, skipped)
        assert result["imported"] == 2
        assert result["already_processed"] == 4
        assert result["skipped"] == 0  # No duplicates
        assert len(result["errors"]) == 0

        # Verify imported items have status=completed (ready for processing)
        item1 = project_db.get_work_item("FND-001")
        assert item1 is not None
        assert item1["status"] == "completed"

        item2 = project_db.get_work_item("FND-002")
        assert item2 is not None
        assert item2["status"] == "completed"

        # Verify non-pending items were NOT imported
        assert project_db.get_work_item("FND-003") is None
        assert project_db.get_work_item("ADM-004") is None

    def test_import_all_mode_preserves_status(self, project_db, sample_jsonl_file):
        """Test importing all items with status preservation (all mode)."""
        result = project_db.import_jsonl(
            file_path=sample_jsonl_file,
            format_id="hank_prd",
            workflow_id="test-workflow",
            source_step_id=1,
            import_mode="all",
        )

        # Should import all 6 items
        assert result["imported"] == 6
        assert result["already_processed"] == 0
        assert len(result["errors"]) == 0

        # Verify status mapping
        # pending/no-status -> completed
        item1 = project_db.get_work_item("FND-001")
        assert item1["status"] == "completed"

        item2 = project_db.get_work_item("FND-002")
        assert item2["status"] == "completed"

        # implemented -> processed
        item3 = project_db.get_work_item("FND-003")
        assert item3["status"] == "processed"

        # dup -> duplicate
        item4 = project_db.get_work_item("ADM-004")
        assert item4["status"] == "duplicate"
        assert item4["duplicate_of"] == "ADM-001"

        # external -> skipped with skip_reason
        item5 = project_db.get_work_item("CHG-001")
        assert item5["status"] == "skipped"
        assert item5["skip_reason"] == "external:claim_cleaner"

        # skipped -> skipped
        item6 = project_db.get_work_item("ANS-099")
        assert item6["status"] == "skipped"
        assert item6["skip_reason"] == "Requires external API not available"

    def test_import_reset_mode(self, project_db, sample_jsonl_file):
        """Test importing all items with status reset (reset mode)."""
        result = project_db.import_jsonl(
            file_path=sample_jsonl_file,
            format_id="hank_prd",
            workflow_id="test-workflow",
            source_step_id=1,
            import_mode="reset",
        )

        # Should import all 6 items
        assert result["imported"] == 6

        # All should have status=completed regardless of source status
        for item_id in ["FND-001", "FND-002", "FND-003", "ADM-004", "CHG-001", "ANS-099"]:
            item = project_db.get_work_item(item_id)
            assert item is not None
            assert item["status"] == "completed"

    def test_title_generated_from_content(self, project_db, sample_jsonl_file):
        """Test that title is auto-generated from story content."""
        project_db.import_jsonl(
            file_path=sample_jsonl_file,
            format_id="hank_prd",
            workflow_id="test-workflow",
            source_step_id=1,
            import_mode="all",
        )

        # Check title is first 100 chars of story
        item = project_db.get_work_item("FND-001")
        assert item["title"] == "System has Patient model for MPI"

        # Check long story gets truncated
        item = project_db.get_work_item("CHG-001")
        assert item["title"].endswith("...")
        assert len(item["title"]) <= 103  # 100 + "..."

    def test_metadata_preserved(self, project_db, sample_jsonl_file):
        """Test that metadata fields are preserved."""
        project_db.import_jsonl(
            file_path=sample_jsonl_file,
            format_id="hank_prd",
            workflow_id="test-workflow",
            source_step_id=1,
            import_mode="all",
        )

        # Check acceptance_criteria in metadata
        item = project_db.get_work_item("FND-001")
        assert item["metadata"] is not None
        metadata = json.loads(item["metadata"]) if isinstance(item["metadata"], str) else item["metadata"]
        assert "acceptance_criteria" in metadata
        assert len(metadata["acceptance_criteria"]) == 2

        # Check impl_notes preserved for implemented items
        item3 = project_db.get_work_item("FND-003")
        metadata3 = json.loads(item3["metadata"]) if isinstance(item3["metadata"], str) else item3["metadata"]
        assert metadata3.get("impl_notes") == "Implemented with full CRUD API"

    def test_category_from_id_prefix(self, project_db, sample_jsonl_file):
        """Test category auto-detection from ID prefix."""
        project_db.import_jsonl(
            file_path=sample_jsonl_file,
            format_id="hank_prd",
            workflow_id="test-workflow",
            source_step_id=1,
            import_mode="all",
        )

        # hank_prd format has id_prefix_to_category=True
        item = project_db.get_work_item("FND-001")
        assert item["category"] == "foundation"  # FND -> foundation from category_mappings

        item = project_db.get_work_item("ANS-099")
        assert item["category"] == "anesthesia"  # ANS -> anesthesia from category_mappings

    def test_malformed_json_line_error(self, project_db, tmp_path):
        """Test handling of malformed JSON lines."""
        file_path = tmp_path / "malformed.jsonl"
        with open(file_path, "w") as f:
            f.write('{"id": "FND-001", "story": "Valid item"}\n')
            f.write('not valid json\n')
            f.write('{"id": "FND-002", "story": "Another valid item"}\n')

        result = project_db.import_jsonl(
            file_path=str(file_path),
            format_id="hank_prd",
            workflow_id="test-workflow",
            source_step_id=1,
            import_mode="all",
        )

        assert result["imported"] == 2
        assert len(result["errors"]) == 1
        assert "Line 2" in result["errors"][0]
        assert "JSON parse error" in result["errors"][0]

    def test_missing_id_field_error(self, project_db, tmp_path):
        """Test handling of items missing required id field."""
        file_path = tmp_path / "no_id.jsonl"
        with open(file_path, "w") as f:
            f.write('{"story": "Item without id"}\n')
            f.write('{"id": "FND-001", "story": "Valid item"}\n')

        result = project_db.import_jsonl(
            file_path=str(file_path),
            format_id="hank_prd",
            workflow_id="test-workflow",
            source_step_id=1,
            import_mode="all",
        )

        assert result["imported"] == 1
        assert len(result["errors"]) == 1
        assert "Missing 'id' field" in result["errors"][0]

    def test_empty_lines_skipped(self, project_db, tmp_path):
        """Test that empty lines are gracefully skipped."""
        file_path = tmp_path / "with_empty.jsonl"
        with open(file_path, "w") as f:
            f.write('{"id": "FND-001", "story": "First item"}\n')
            f.write('\n')
            f.write('   \n')
            f.write('{"id": "FND-002", "story": "Second item"}\n')

        result = project_db.import_jsonl(
            file_path=str(file_path),
            format_id="hank_prd",
            workflow_id="test-workflow",
            source_step_id=1,
            import_mode="all",
        )

        assert result["imported"] == 2
        assert len(result["errors"]) == 0

    def test_duplicate_items_skipped(self, project_db, tmp_path):
        """Test that duplicate items (same ID) are skipped."""
        file_path = tmp_path / "duplicates.jsonl"
        with open(file_path, "w") as f:
            f.write('{"id": "FND-001", "story": "First version"}\n')
            f.write('{"id": "FND-001", "story": "Duplicate version"}\n')
            f.write('{"id": "FND-002", "story": "Different item"}\n')

        result = project_db.import_jsonl(
            file_path=str(file_path),
            format_id="hank_prd",
            workflow_id="test-workflow",
            source_step_id=1,
            import_mode="all",
        )

        assert result["imported"] == 2
        assert result["skipped"] == 1  # One duplicate

        # First version should be kept
        item = project_db.get_work_item("FND-001")
        assert "First version" in item["content"]

    def test_file_not_found_error(self, project_db):
        """Test FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            project_db.import_jsonl(
                file_path="/nonexistent/path/file.jsonl",
                format_id="hank_prd",
                workflow_id="test-workflow",
                source_step_id=1,
            )

    def test_invalid_format_error(self, project_db, sample_jsonl_file):
        """Test ValueError for invalid format ID."""
        with pytest.raises(ValueError) as exc_info:
            project_db.import_jsonl(
                file_path=sample_jsonl_file,
                format_id="nonexistent_format",
                workflow_id="test-workflow",
                source_step_id=1,
            )
        assert "not found" in str(exc_info.value)

    def test_invalid_import_mode_error(self, project_db, sample_jsonl_file):
        """Test ValueError for invalid import_mode."""
        with pytest.raises(ValueError) as exc_info:
            project_db.import_jsonl(
                file_path=sample_jsonl_file,
                format_id="hank_prd",
                workflow_id="test-workflow",
                source_step_id=1,
                import_mode="invalid_mode",
            )
        assert "Invalid import_mode" in str(exc_info.value)
