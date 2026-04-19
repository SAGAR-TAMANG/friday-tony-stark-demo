"""Skills tools — Dynamic skill discovery and management."""

from __future__ import annotations

from pathlib import Path

from friday.core.skill_registry import get_skill_registry


# Initialize skill registry
_skill_registry = get_skill_registry()


def register(mcp):
    """Register skill management tools with MCP server."""

    @mcp.tool()
    async def skill_discover(query: str = "") -> str:
        """Discover available skills.

        Args:
            query: Search query (empty for all skills)
        """
        skills = _skill_registry.discover(query if query else "")

        if not skills:
            return f"[SKILLS] No skills found for query: {query}" if query else "[SKILLS] No skills registered"

        lines = [f"[SKILLS] Available skills ({len(skills)}):\n"]
        for skill in skills:
            status = "✓ loaded" if skill.name in _skill_registry.loaded_skills else "○ available"
            lines.append(f"  {skill.name} v{skill.version} [{status}]")
            lines.append(f"    {skill.description}")
            if skill.tags:
                lines.append(f"    Tags: {', '.join(skill.tags)}")
            lines.append("")

        return "\n".join(lines)

    @mcp.tool()
    async def skill_load(skill_name: str) -> str:
        """Load a skill and register its tools.

        Args:
            skill_name: Name of the skill to load
        """
        # Note: In a real implementation, we'd need access to the MCP instance
        # This is a simplified version
        manifest = _skill_registry.get(skill_name)

        if not manifest:
            return f"[SKILLS ERROR] Skill not found: {skill_name}"

        if skill_name in _skill_registry.loaded_skills:
            return f"[SKILLS] Skill already loaded: {skill_name}"

        # Mark as loaded (actual loading requires MCP instance)
        return (
            f"[SKILLS] Skill ready to load: {skill_name}\n"
            f"  Version: {manifest.version}\n"
            f"  Author: {manifest.author}\n"
            f"  Entry: {manifest.entry_point}\n"
            f"  Run 'uv run friday' with --load-skill {skill_name}"
        )

    @mcp.tool()
    async def skill_info(skill_name: str) -> str:
        """Get detailed info about a skill.

        Args:
            skill_name: Name of the skill
        """
        skill = _skill_registry.get(skill_name)

        if not skill:
            return f"[SKILLS ERROR] Skill not found: {skill_name}"

        lines = [
            f"[SKILLS] Skill: {skill.name}",
            f"  Version: {skill.version}",
            f"  Author: {skill.author}",
            f"  Description: {skill.description}",
            f"  Source: {skill.source}",
            f"  Entry Point: {skill.entry_point}",
            f"  Status: {'loaded' if skill_name in _skill_registry.loaded_skills else 'available'}",
        ]

        if skill.dependencies:
            lines.append(f"  Dependencies: {', '.join(skill.dependencies)}")
        if skill.required_capabilities:
            lines.append(f"  Required Capabilities: {', '.join(skill.required_capabilities)}")
        if skill.tags:
            lines.append(f"  Tags: {', '.join(skill.tags)}")

        return "\n".join(lines)

    @mcp.tool()
    async def skill_reload() -> str:
        """Reload the skill index from disk."""
        _skill_registry.reload()
        count = len(_skill_registry.skills)
        return f"[SKILLS] Reloaded skill index. {count} skill(s) registered."

    @mcp.tool()
    async def skill_create_template(name: str, description: str) -> str:
        """Create a skill template directory.

        Args:
            name: Skill name
            description: Skill description
        """
        import os

        friday_home = Path(os.getenv("FRIDAY_HOME", Path.home() / ".friday"))
        skill_dir = friday_home / "skills" / name

        if skill_dir.exists():
            return f"[SKILLS ERROR] Skill directory already exists: {skill_dir}"

        skill_dir.mkdir(parents=True)

        # Create skill.toml
        toml_content = f"""[skill]
name = "{name}"
version = "0.1.0"
description = "{description}"
author = "user"
source = "local"
entry_point = "main.py"
dependencies = []
required_capabilities = []
tags = ["custom"]
enabled = true
"""

        (skill_dir / "skill.toml").write_text(toml_content, "utf-8")

        # Create main.py template
        py_content = '''"""''' + f"""{name} skill — {description}""" + '''"""

from __future__ import annotations


def register(mcp):
    """Register tools with MCP server."""

    @mcp.tool()
    async def ''' + name.replace("-", "_") + '''_example() -> str:
        """Example tool from ''' + name + ''' skill."""
        return "Hello from ''' + name + '''!"
'''

        (skill_dir / "main.py").write_text(py_content, "utf-8")

        return (
            f"[SKILLS] Created skill template: {name}\n"
            f"  Location: {skill_dir}\n"
            f"  Files: skill.toml, main.py\n"
            f"  Edit these files, then reload skills."
        )
