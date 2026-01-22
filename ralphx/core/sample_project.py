"""Sample project creation for RalphX first-run experience.

Creates a sample "Excuse Generator" project when users first install RalphX,
demonstrating how workflows work with design documents, stories, and guardrails.
"""

import json
import logging
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from ralphx.core.workspace import get_workspace_path

logger = logging.getLogger(__name__)

# Sample project name and directory
SAMPLE_PROJECT_NAME = "Excuse-Generator"
SAMPLE_PROJECT_DIR_NAME = "excuse-generator"


def get_sample_project_source_path() -> Path:
    """Get path to bundled sample project files.

    Returns:
        Path to ralphx/examples/sample_project/ directory.
    """
    return Path(__file__).parent.parent / "examples" / "sample_project"


def get_samples_directory() -> Path:
    """Get the samples directory within the RalphX workspace.

    Returns:
        Path to ~/.ralphx/samples/
    """
    samples_dir = get_workspace_path() / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    return samples_dir


def get_sample_project_target_path() -> Path:
    """Get target path for sample project.

    Returns:
        Path to ~/.ralphx/samples/excuse-generator/
    """
    return get_samples_directory() / SAMPLE_PROJECT_DIR_NAME


def _init_git_repo(project_path: Path) -> bool:
    """Initialize a git repository in the project directory.

    Args:
        project_path: Path to the project directory.

    Returns:
        True if git repo was initialized, False if git not available.
    """
    try:
        # Check if git is available
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=project_path,
            capture_output=True,
            timeout=10,
        )

        # Create initial commit with sample files
        subprocess.run(
            ["git", "add", "."],
            cwd=project_path,
            capture_output=True,
            timeout=10,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit: RalphX sample project"],
            cwd=project_path,
            capture_output=True,
            timeout=10,
        )

        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _create_workflow_with_stories(
    project_db,
    workflow_id: str,
    template_id: str,
    stories_path: Path,
) -> Optional[str]:
    """Create a workflow from template and populate with sample stories.

    Args:
        project_db: ProjectDatabase instance.
        workflow_id: ID for the new workflow.
        template_id: Template ID to base workflow on.
        stories_path: Path to stories.jsonl file.

    Returns:
        Workflow ID if created, None on error.
    """
    try:
        # Seed templates if empty
        project_db.seed_workflow_templates_if_empty()

        # Get template to create steps from
        template = project_db.get_workflow_template(template_id)
        if not template:
            logger.warning(f"Template '{template_id}' not found")
            return None

        # Create workflow (namespace parameter removed in schema v16)
        workflow = project_db.create_workflow(
            id=workflow_id,
            name="Build Excuse Generator",
            template_id=template_id,
            status="draft",
        )

        # Create steps from template phases
        created_steps = []
        for phase in template.get("phases", []):
            step = project_db.create_workflow_step(
                workflow_id=workflow_id,
                step_number=phase["number"],
                name=phase["name"],
                step_type=phase["type"],
                config={
                    "description": phase.get("description"),
                    "loopType": phase.get("loopType"),
                    "inputs": phase.get("inputs", []),
                    "outputs": phase.get("outputs", []),
                    "skippable": phase.get("skippable", False),
                    "skipCondition": phase.get("skipCondition"),
                },
                status="pending",
            )
            created_steps.append(step)

        # Find the Story Generation step (step 1 in from-design-doc template)
        story_step = None
        for step in created_steps:
            if step["step_number"] == 1:
                story_step = step
                break

        if not story_step:
            logger.warning("Could not find Story Generation step")
            return workflow_id

        # Import stories from JSONL file
        if stories_path.exists():
            story_count = _import_stories(
                project_db,
                workflow_id=workflow_id,
                source_step_id=story_step["id"],
                stories_path=stories_path,
            )

            # Create a completed run record to track the imported stories
            if story_count > 0:
                run_id = f"run-sample-{uuid.uuid4().hex[:8]}"
                project_db.create_run(
                    id=run_id,
                    loop_name="sample-import",
                    workflow_id=workflow_id,
                    step_id=story_step["id"],
                )
                # Mark run as completed with story count
                from datetime import datetime
                project_db.update_run(
                    run_id,
                    status="completed",
                    completed_at=datetime.utcnow().isoformat(),
                    iterations_completed=1,
                    items_generated=story_count,
                )

            # Mark Story Generation step as completed since stories are pre-populated
            project_db.update_workflow_step(
                story_step["id"],
                status="completed",
            )

        return workflow_id

    except Exception as e:
        logger.error(f"Failed to create workflow: {e}")
        return None


def _import_stories(
    project_db,
    workflow_id: str,
    source_step_id: int,
    stories_path: Path,
) -> int:
    """Import stories from JSONL file as work items.

    Args:
        project_db: ProjectDatabase instance.
        workflow_id: Parent workflow ID.
        source_step_id: Step ID that "created" these items.
        stories_path: Path to stories.jsonl file.

    Returns:
        Number of stories imported.
    """
    count = 0
    try:
        with open(stories_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    story = json.loads(line)

                    # Build content from story data
                    content_parts = [story.get("description", "")]

                    # Add acceptance criteria if present
                    criteria = story.get("acceptance_criteria", [])
                    if criteria:
                        content_parts.append("\n\n## Acceptance Criteria")
                        for criterion in criteria:
                            content_parts.append(f"- {criterion}")

                    content = "\n".join(content_parts)

                    # Determine priority (convert string to int if needed)
                    priority = story.get("priority")
                    if priority == "high":
                        priority = 1
                    elif priority == "medium":
                        priority = 2
                    elif priority == "low":
                        priority = 3
                    elif isinstance(priority, str):
                        priority = 2  # default

                    # Create work item with status "completed" so it's ready for Implementation
                    project_db.create_work_item(
                        id=story.get("id", f"story-{uuid.uuid4().hex[:8]}"),
                        workflow_id=workflow_id,
                        source_step_id=source_step_id,
                        content=content,
                        title=story.get("title"),
                        priority=priority,
                        category=story.get("category"),
                        item_type="story",
                        metadata={
                            "acceptance_criteria": story.get("acceptance_criteria", []),
                            "dependencies": story.get("dependencies", []),
                        },
                        status="completed",  # Ready for next step to consume
                    )
                    count += 1

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse story line: {e}")
                    continue

    except Exception as e:
        logger.error(f"Failed to import stories: {e}")

    return count


def create_sample_project() -> Optional[str]:
    """Create the sample project for first-run experience.

    This function:
    1. Creates ~/RalphX-Sample-Project/ directory
    2. Copies sample files (README, DESIGN.md, guardrails, stories)
    3. Initializes git repository (if git available)
    4. Registers project with RalphX
    5. Creates a workflow from "from-design-doc" template
    6. Pre-populates with sample stories

    Returns:
        Project slug if created successfully, None on error.
    """
    from ralphx.core.project import ProjectManager
    from ralphx.core.project_db import ProjectDatabase

    source_path = get_sample_project_source_path()
    target_path = get_sample_project_target_path()

    # Check if source files exist
    if not source_path.exists():
        logger.warning(f"Sample project source not found: {source_path}")
        return None

    # Check if target already exists
    if target_path.exists():
        logger.info(f"Sample project directory already exists: {target_path}")
        return None

    try:
        # Create target directory
        target_path.mkdir(parents=True, exist_ok=True)

        # Copy sample files
        for source_file in source_path.iterdir():
            if source_file.is_file():
                shutil.copy2(source_file, target_path / source_file.name)

        logger.info(f"Created sample project at: {target_path}")

        # Initialize git repo
        git_initialized = _init_git_repo(target_path)
        if git_initialized:
            logger.info("Initialized git repository")
        else:
            logger.info("Git not available, skipping repository initialization")

        # Register project with RalphX
        pm = ProjectManager()

        try:
            project = pm.add_project(
                path=target_path,
                name=SAMPLE_PROJECT_NAME,
                design_doc="DESIGN.md",
                slug="excuse-generator",
            )
            logger.info(f"Registered sample project: {project.slug}")

            # Create workflow with pre-populated stories
            project_db = pm.get_project_db(target_path)
            workflow_id = f"wf-sample-{uuid.uuid4().hex[:8]}"

            _create_workflow_with_stories(
                project_db,
                workflow_id=workflow_id,
                template_id="from-design-doc",
                stories_path=target_path / "stories.jsonl",
            )
            logger.info("Created sample workflow with pre-populated stories")

            # Add design doc as workflow resource
            try:
                design_doc_path = target_path / "DESIGN.md"
                if design_doc_path.exists():
                    project_db.create_workflow_resource(
                        workflow_id=workflow_id,
                        resource_type="design_doc",
                        name="Excuse Generator Design",
                        content=design_doc_path.read_text(),
                        source="manual",
                        enabled=True,
                    )

                # Add guardrails as workflow resource
                guardrails_path = target_path / "guardrails.md"
                if guardrails_path.exists():
                    project_db.create_workflow_resource(
                        workflow_id=workflow_id,
                        resource_type="guardrails",
                        name="Project Guardrails",
                        content=guardrails_path.read_text(),
                        source="manual",
                        enabled=True,
                    )
            except Exception as e:
                logger.warning(f"Failed to add workflow resources: {e}")

            return project.slug

        except FileExistsError:
            logger.info("Sample project already registered")
            return "excuse-generator"

    except Exception as e:
        logger.error(f"Failed to create sample project: {e}")
        # Clean up on failure
        if target_path.exists():
            try:
                shutil.rmtree(target_path)
            except Exception:
                pass
        return None


def ensure_sample_project_created() -> bool:
    """Ensure sample project is created on first run.

    Uses global database settings to track if sample was already created.

    Returns:
        True if sample project was created or already exists, False on error.
    """
    from ralphx.core.global_db import GlobalDatabase

    global_db = GlobalDatabase()

    # Check if already created
    if global_db.get_setting("sample_project_created") is not None:
        return True

    # Create sample project
    result = create_sample_project()

    if result:
        # Mark as created
        global_db.set_setting("sample_project_created", "true")
        logger.info("Sample project setup complete")
        return True

    # Even if creation failed (e.g., directory exists), mark as attempted
    # to avoid repeated attempts
    global_db.set_setting("sample_project_created", "attempted")
    return False
