"""Workflow executor for orchestrating multi-step workflows.

This module provides the WorkflowExecutor class which coordinates execution
of workflow steps, creating loops for autonomous steps and managing
step transitions.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from ralphx.core.executor import LoopExecutor
from ralphx.core.loop import LoopLoader
from ralphx.core.project import Project
from ralphx.core.project_db import ProjectDatabase
from ralphx.core.resources import ResourceManager
from ralphx.models.loop import LoopConfig


class WorkflowExecutor:
    """Orchestrates multi-step workflow execution.

    The WorkflowExecutor is responsible for:
    - Starting and advancing workflow steps
    - Creating loops for autonomous steps
    - Injecting artifacts from previous steps into loop context
    - Monitoring loop completion and triggering step advancement
    - Handling both interactive and autonomous step types
    """

    def __init__(
        self,
        project: Project,
        db: ProjectDatabase,
        workflow_id: str,
        on_step_change: Optional[Callable[[str, int, str], None]] = None,
    ):
        """Initialize workflow executor.

        Args:
            project: Project instance.
            db: Project database instance.
            workflow_id: ID of the workflow to execute.
            on_step_change: Optional callback for step status changes.
                           Called with (workflow_id, step_number, new_status).
        """
        self.project = project
        self.db = db
        self.workflow_id = workflow_id
        self._on_step_change = on_step_change
        self._running_executors: dict[int, LoopExecutor] = {}

    def get_workflow(self) -> Optional[dict]:
        """Get the current workflow."""
        return self.db.get_workflow(self.workflow_id)

    def get_current_step(self) -> Optional[dict]:
        """Get the current step of the workflow."""
        workflow = self.get_workflow()
        if not workflow:
            return None
        return self.db.get_workflow_step_by_number(
            self.workflow_id, workflow["current_step"]
        )

    def get_steps(self) -> list[dict]:
        """Get all steps for the workflow."""
        return self.db.list_workflow_steps(self.workflow_id)

    async def start_workflow(self) -> dict:
        """Start the workflow execution.

        Activates the workflow and starts the first pending step.

        Returns:
            The updated workflow dict.

        Raises:
            ValueError: If workflow not found or already completed.
        """
        workflow = self.get_workflow()
        if not workflow:
            raise ValueError(f"Workflow not found: {self.workflow_id}")

        if workflow["status"] == "completed":
            raise ValueError("Workflow already completed")

        if workflow["status"] not in ("draft", "paused"):
            raise ValueError(f"Workflow is already {workflow['status']}")

        # Find the first pending step
        steps = self.get_steps()
        first_pending = None
        for step in steps:
            if step["status"] == "pending":
                first_pending = step
                break

        if not first_pending:
            raise ValueError("No pending steps to start")

        # Update workflow status
        self.db.update_workflow(
            self.workflow_id,
            status="active",
            current_step=first_pending["step_number"],
        )

        # Start the first step
        await self._start_step(first_pending)

        return self.get_workflow()

    async def _start_step(self, step: dict) -> None:
        """Start executing a workflow step.

        For interactive steps, just marks as started (UI handles interaction).
        For autonomous steps, creates and starts the loop.

        Args:
            step: The step dict to start.
        """
        step_id = step["id"]
        step_type = step["step_type"]

        # Mark step as active
        self.db.start_workflow_step(step_id)
        self._emit_step_change(step["step_number"], "active")

        if step_type == "interactive":
            # Interactive steps are handled by the UI (PlanningChat, etc.)
            # Just mark as started, the UI will call complete_step when done
            pass

        elif step_type == "autonomous":
            # Create and start a loop for this step
            await self._start_autonomous_step(step)

    async def _start_autonomous_step(self, step: dict) -> None:
        """Start an autonomous step by creating and running a loop.

        Args:
            step: The step dict.
        """
        step_id = step["id"]
        step_config = step.get("config", {})

        # Determine loop type from step config
        loop_type = step_config.get("loopType", "consumer")

        # Generate loop name (must match pattern ^[a-z][a-z0-9_]*$)
        wf_id_clean = self.workflow_id.replace("-", "")[:8]
        loop_name = f"wf_{wf_id_clean}_step{step['step_number']}"

        # Check if loop already exists (resumed workflow)
        existing = self.db.get_loop(loop_name)
        if existing:
            loop_config = self._load_loop_config(existing)
        else:
            # Create new loop for this step
            loop_config = self._create_step_loop(step, loop_name, loop_type)

        if not loop_config:
            raise ValueError(f"Failed to create loop config for step {step_id}")

        # Inject artifacts from previous steps
        await self._inject_artifacts(loop_config, step)

        # Determine which step to consume from (for consumer loops)
        # Two patterns supported:
        # 1. Multi-step: consume from previous step (generator → consumer)
        # 2. Single-step: consume from own step ID (for imported items)
        consume_from_step_id = None
        if loop_type == "consumer":
            if step["step_number"] > 1:
                # Multi-step workflow: consume from previous step
                prev_step = self.db.get_workflow_step_by_number(
                    self.workflow_id, step["step_number"] - 1
                )
                if prev_step:
                    consume_from_step_id = prev_step["id"]
            else:
                # Single-step consumer: consume from own step ID
                # This supports importing items directly for this step
                consume_from_step_id = step["id"]

        # Check if architecture-first mode is enabled
        architecture_first = step_config.get("architecture_first", False)

        # Create and start executor
        executor = LoopExecutor(
            project=self.project,
            loop_config=loop_config,
            db=self.db,
            workflow_id=self.workflow_id,
            step_id=step_id,
            consume_from_step_id=consume_from_step_id,
            architecture_first=architecture_first,
        )

        self._running_executors[step_id] = executor

        # Run executor in background
        asyncio.create_task(self._run_loop_and_advance(executor, step))

    async def _run_loop_and_advance(
        self, executor: LoopExecutor, step: dict
    ) -> None:
        """Run a loop and advance to next step when complete.

        Args:
            executor: The loop executor.
            step: The step dict.
        """
        from ralphx.models.run import RunStatus

        step_id = step["id"]
        step_config = step.get("config", {})

        try:
            run = await executor.run()

            # Only advance if the run was successful
            if run.status == RunStatus.ERROR:
                # Mark step as failed (store error in artifacts)
                self.db.update_workflow_step(
                    step_id,
                    status="error",
                    artifacts={"error": run.error_message or "Loop execution failed"},
                )
                self._emit_step_change(step["step_number"], "error")
                return

            if run.status == RunStatus.ABORTED:
                # Keep step active - user can resume
                return

            # Check if step should auto-advance on successful completion
            auto_advance = step_config.get("auto_advance", True)
            if auto_advance:
                await self.complete_step(step_id)

        finally:
            self._running_executors.pop(step_id, None)

    def _create_step_loop(
        self, step: dict, loop_name: str, loop_type: str
    ) -> Optional[LoopConfig]:
        """Create a loop configuration for an autonomous step.

        Args:
            step: The step dict.
            loop_name: Name for the new loop.
            loop_type: Type of loop (generator, consumer).

        Returns:
            LoopConfig for the new loop, or None if creation failed.
        """
        from ralphx.core.loop_templates import (
            generate_simple_planning_config,
            generate_simple_implementation_config,
        )

        step_config = step.get("config", {})

        # Extract loop limits from step config
        max_iterations = step_config.get("max_iterations")
        cooldown = step_config.get("cooldown_between_iterations")
        max_errors = step_config.get("max_consecutive_errors")

        # Generate YAML config based on loop type
        if loop_type == "generator":
            config_yaml = generate_simple_planning_config(
                name=loop_name,
                display_name=step.get("name", "Story Generation"),
                description=step_config.get("description", ""),
                max_iterations=max_iterations,
                cooldown_between_iterations=cooldown,
                max_consecutive_errors=max_errors,
            )
        else:
            config_yaml = generate_simple_implementation_config(
                name=loop_name,
                display_name=step.get("name", "Implementation"),
                description=step_config.get("description", ""),
                max_iterations=max_iterations,
                cooldown_between_iterations=cooldown,
                max_consecutive_errors=max_errors,
            )

        # Save to database
        self.db.create_loop(
            id=f"loop-{uuid.uuid4().hex[:8]}",
            name=loop_name,
            config_yaml=config_yaml,
            workflow_id=self.workflow_id,
            step_id=step["id"],
        )

        # Also write YAML file for LoopLoader
        loops_dir = Path(self.project.path) / ".ralphx" / "loops"
        loops_dir.mkdir(parents=True, exist_ok=True)
        config_path = loops_dir / f"{loop_name}.yaml"
        config_path.write_text(config_yaml)

        # Create prompt files (required by the loop config)
        self._create_loop_prompt_files(loop_name, loop_type, step)

        # Load and return config
        loader = LoopLoader(db=self.db)
        return loader.get_loop(loop_name)

    def _load_loop_config(self, loop_record: dict) -> Optional[LoopConfig]:
        """Load LoopConfig from a database loop record.

        Args:
            loop_record: Dict from db.get_loop().

        Returns:
            LoopConfig or None.
        """
        loader = LoopLoader(db=self.db)
        return loader.get_loop(loop_record["name"])

    # Maximum allowed size for custom prompts (50KB)
    MAX_CUSTOM_PROMPT_LENGTH = 50000

    def _create_loop_prompt_files(
        self, loop_name: str, loop_type: str, step: dict
    ) -> None:
        """Create prompt template files for an auto-generated loop.

        The simple config generators reference prompt files that don't exist.
        This method creates those files with default content, or uses a custom
        prompt if specified in the step config.

        Args:
            loop_name: Name of the loop.
            loop_type: Type of loop (generator, consumer).
            step: The step dict containing config (may include customPrompt or template).
        """
        from ralphx.core.loop_templates import (
            PLANNING_EXTRACT_PROMPT,
            IMPLEMENTATION_IMPLEMENT_PROMPT,
            WEBGEN_REQUIREMENTS_PROMPT,
        )

        loop_dir = Path(self.project.path) / ".ralphx" / "loops" / loop_name
        prompts_dir = loop_dir / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)

        # Check for custom prompt in step config
        step_config = step.get("config", {})
        custom_prompt = step_config.get("customPrompt")

        # Validate custom prompt size if provided
        if custom_prompt:
            if len(custom_prompt) > self.MAX_CUSTOM_PROMPT_LENGTH:
                raise ValueError(
                    f"Custom prompt exceeds maximum length of {self.MAX_CUSTOM_PROMPT_LENGTH} characters"
                )
            # Treat empty/whitespace-only as no custom prompt
            if not custom_prompt.strip():
                custom_prompt = None

        # Determine prompt content and file based on template or loop_type
        template = step_config.get("template")

        if loop_type == "generator":
            prompt_file = prompts_dir / "planning.md"
            if custom_prompt:
                prompt_content = custom_prompt
            elif template == "webgen_requirements":
                prompt_content = WEBGEN_REQUIREMENTS_PROMPT
            else:
                prompt_content = PLANNING_EXTRACT_PROMPT
        else:
            prompt_file = prompts_dir / "implement.md"
            prompt_content = custom_prompt or IMPLEMENTATION_IMPLEMENT_PROMPT

        prompt_file.write_text(prompt_content.strip())

    async def _inject_artifacts(
        self, loop_config: LoopConfig, step: dict
    ) -> None:
        """Inject artifacts from previous steps into loop context.

        This adds design docs, guardrails, and other artifacts from
        interactive planning steps into the loop's resources.

        The method uses get_effective_resources_for_step() to respect
        step-level resource configurations (overrides, disables, adds).

        Artifacts are:
        1. Migrated from planning sessions to workflow_resources (if needed)
        2. Merged with step-level configurations
        3. Injected into the loop's context via loop_resources

        Args:
            loop_config: The loop configuration to inject into.
            step: The current step dict.
        """
        step_id = step["id"]

        # First, migrate any planning session artifacts not yet in workflow_resources
        # This ensures they're available for the effective resources merge
        steps = self.get_steps()
        for prev_step in steps:
            if prev_step["step_number"] >= step["step_number"]:
                break

            if prev_step["step_type"] == "interactive":
                # Get planning session for this step
                session = self.db.get_planning_session_by_step(prev_step["id"])
                if session and session.get("artifacts"):
                    artifacts = session["artifacts"]

                    # Check if design doc already exists in workflow_resources
                    if artifacts.get("design_doc"):
                        existing = self.db.list_workflow_resources(
                            self.workflow_id, resource_type="design_doc"
                        )
                        if not existing:
                            # Save to workflow_resources
                            self.db.create_workflow_resource(
                                workflow_id=self.workflow_id,
                                resource_type="design_doc",
                                name=f"Design Doc (Step {prev_step['step_number']})",
                                content=artifacts["design_doc"],
                                source="planning_step",
                            )

                    # Check if guardrails already exists in workflow_resources
                    if artifacts.get("guardrails"):
                        existing = self.db.list_workflow_resources(
                            self.workflow_id, resource_type="guardrail"
                        )
                        if not existing:
                            # Save to workflow_resources
                            self.db.create_workflow_resource(
                                workflow_id=self.workflow_id,
                                resource_type="guardrail",
                                name=f"Guardrails (Step {prev_step['step_number']})",
                                content=artifacts["guardrails"],
                                source="planning_step",
                            )

        # Now get effective resources for this step (workflow + step configs merged)
        effective_resources = self.db.get_effective_resources_for_step(
            step_id, self.workflow_id
        )

        # Get existing loop resources to avoid duplicates on resume
        existing_loop_resources = self.db.list_loop_resources(
            loop_name=loop_config.name
        )
        existing_names = {r["name"] for r in existing_loop_resources}

        # Inject effective resources into the loop (skip if already exists)
        for res in effective_resources:
            res_name = res.get("name", "Unnamed Resource")

            # Skip if this resource was already injected (e.g., workflow resume)
            if res_name in existing_names:
                continue

            resource_type = res.get("resource_type", "custom")
            content = res.get("content")
            file_path = res.get("file_path")

            # Determine injection position based on resource type
            if resource_type == "design_doc":
                position = "after_design_doc"
                priority = 10
            elif resource_type == "guardrail":
                position = "before_task"
                priority = 20
            elif resource_type == "prompt":
                position = "before_prompt"
                priority = 5
            else:
                position = "after_design_doc"
                priority = res.get("priority", 50)

            # Handle both inline content and file-based resources
            if file_path:
                self.db.create_loop_resource(
                    loop_name=loop_config.name,
                    resource_type=resource_type,
                    name=res_name,
                    injection_position=position,
                    source_type="project_file",
                    source_path=file_path,
                    enabled=True,
                    priority=priority,
                )
            else:
                self.db.create_loop_resource(
                    loop_name=loop_config.name,
                    resource_type=resource_type,
                    name=res_name,
                    injection_position=position,
                    source_type="inline",
                    inline_content=content or "",
                    enabled=True,
                    priority=priority,
                )

    async def complete_step(
        self,
        step_id: int,
        artifacts: Optional[dict] = None,
    ) -> dict:
        """Mark a step as completed and advance to next step.

        Args:
            step_id: ID of the step to complete.
            artifacts: Optional artifacts produced by this step.

        Returns:
            Updated workflow dict.

        Raises:
            ValueError: If step not found or not active.
        """
        step = self.db.get_workflow_step(step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        if step["status"] != "active":
            raise ValueError(f"Step is not active: {step['status']}")

        # Complete the step
        self.db.complete_workflow_step(step_id, artifacts=artifacts)
        self._emit_step_change(step["step_number"], "completed")

        # Find and start next step
        next_step = self.db.get_workflow_step_by_number(
            self.workflow_id, step["step_number"] + 1
        )

        if next_step:
            # Update workflow current step
            self.db.update_workflow(
                self.workflow_id, current_step=next_step["step_number"]
            )
            await self._start_step(next_step)
        else:
            # No more steps - complete the workflow
            self.db.update_workflow(self.workflow_id, status="completed")

        return self.get_workflow()

    async def skip_step(
        self,
        step_id: int,
        reason: Optional[str] = None,
    ) -> dict:
        """Skip a step and advance to next.

        Args:
            step_id: ID of the step to skip.
            reason: Optional reason for skipping.

        Returns:
            Updated workflow dict.
        """
        step = self.db.get_workflow_step(step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        step_config = step.get("config", {})
        if not step_config.get("skippable", False):
            raise ValueError("This step cannot be skipped")

        # Skip the step
        self.db.skip_workflow_step(step_id)
        self._emit_step_change(step["step_number"], "skipped")

        # Find and start next step
        next_step = self.db.get_workflow_step_by_number(
            self.workflow_id, step["step_number"] + 1
        )

        if next_step:
            self.db.update_workflow(
                self.workflow_id, current_step=next_step["step_number"]
            )
            await self._start_step(next_step)
        else:
            self.db.update_workflow(self.workflow_id, status="completed")

        return self.get_workflow()

    async def pause_workflow(self) -> dict:
        """Pause the workflow.

        Stops any running loops and pauses the workflow.

        Returns:
            Updated workflow dict.
        """
        workflow = self.get_workflow()
        if not workflow:
            raise ValueError(f"Workflow not found: {self.workflow_id}")

        if workflow["status"] != "active":
            raise ValueError(f"Cannot pause workflow in status: {workflow['status']}")

        # Stop running executors
        for executor in self._running_executors.values():
            executor.stop()

        self.db.update_workflow(self.workflow_id, status="paused")
        return self.get_workflow()

    async def resume_workflow(self) -> dict:
        """Resume a paused workflow.

        Resumes execution from the current step.

        Returns:
            Updated workflow dict.
        """
        workflow = self.get_workflow()
        if not workflow:
            raise ValueError(f"Workflow not found: {self.workflow_id}")

        if workflow["status"] != "paused":
            raise ValueError(f"Cannot resume workflow in status: {workflow['status']}")

        self.db.update_workflow(self.workflow_id, status="active")

        # Resume current step
        current_step = self.get_current_step()
        if current_step and current_step["status"] == "active":
            if current_step["step_type"] == "autonomous":
                await self._start_autonomous_step(current_step)

        return self.get_workflow()

    def _emit_step_change(self, step_number: int, new_status: str) -> None:
        """Emit step change callback if registered."""
        if self._on_step_change:
            self._on_step_change(self.workflow_id, step_number, new_status)
