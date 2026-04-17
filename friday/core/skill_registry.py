"""Skill Registry — OpenJarvis pattern for dynamic skill discovery and loading.

Skills are self-contained modules that can be discovered at runtime
and loaded into FRIDAY's tool set.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


@dataclass
class SkillManifest:
    """Metadata for a skill."""
    name: str
    version: str
    description: str
    author: str
    source: str
    entry_point: str  # Python file to load
    dependencies: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "SkillManifest":
        return cls(
            name=data.get("name", ""),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            source=data.get("source", ""),
            entry_point=data.get("entry_point", ""),
            dependencies=data.get("dependencies", []),
            required_capabilities=data.get("required_capabilities", []),
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "source": self.source,
            "entry_point": self.entry_point,
            "dependencies": self.dependencies,
            "required_capabilities": self.required_capabilities,
            "tags": self.tags,
            "enabled": self.enabled,
        }


class SkillRegistry:
    """Registry for discovering and loading skills.

    Pattern from OpenJarvis:
    - Scan directories for skill.toml files
    - Load skills dynamically
    - Track dependencies and capabilities
    """

    def __init__(self, skills_dir: Path):
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, SkillManifest] = {}
        self.loaded_skills: dict[str, Any] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Load skill manifests from skills directory."""
        if not self.skills_dir.exists():
            logger.info(f"Skills directory not found: {self.skills_dir}")
            return

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            manifest_file = skill_dir / "skill.toml"
            if manifest_file.exists():
                try:
                    with open(manifest_file, "rb") as f:
                        data = tomllib.load(f)
                    manifest = SkillManifest.from_dict(data.get("skill", {}))
                    manifest.entry_point = str(skill_dir / manifest.entry_point)
                    self.skills[manifest.name] = manifest
                    logger.info(f"Registered skill: {manifest.name} v{manifest.version}")
                except Exception as e:
                    logger.error(f"Failed to load skill from {skill_dir}: {e}")

    def discover(self, query: str = "") -> list[SkillManifest]:
        """Search skills by name, description, or tags."""
        if not query:
            return list(self.skills.values())

        q = query.lower()
        results = []
        for skill in self.skills.values():
            if (
                q in skill.name.lower()
                or q in skill.description.lower()
                or any(q in tag.lower() for tag in skill.tags)
            ):
                results.append(skill)
        return results

    def get(self, name: str) -> Optional[SkillManifest]:
        """Get a skill manifest by name."""
        return self.skills.get(name)

    def load(self, name: str, mcp: Any) -> bool:
        """Load a skill and register its tools with MCP.

        Args:
            name: Skill name
            mcp: MCP server instance

        Returns:
            True if loaded successfully
        """
        manifest = self.skills.get(name)
        if not manifest:
            logger.error(f"Skill not found: {name}")
            return False

        if not manifest.enabled:
            logger.warning(f"Skill is disabled: {name}")
            return False

        if name in self.loaded_skills:
            logger.info(f"Skill already loaded: {name}")
            return True

        try:
            # Load the skill module
            spec = importlib.util.spec_from_file_location(
                f"friday.skill.{name}",
                manifest.entry_point,
            )
            if spec is None or spec.loader is None:
                logger.error(f"Could not load skill module: {manifest.entry_point}")
                return False

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Register with MCP
            if hasattr(module, "register"):
                module.register(mcp)
                self.loaded_skills[name] = module
                logger.info(f"Loaded skill: {name}")
                return True
            else:
                logger.error(f"Skill {name} has no register() function")
                return False

        except Exception as e:
            logger.error(f"Failed to load skill {name}: {e}")
            return False

    def unload(self, name: str) -> bool:
        """Unload a skill."""
        if name in self.loaded_skills:
            del self.loaded_skills[name]
            logger.info(f"Unloaded skill: {name}")
            return True
        return False

    def list_skills(self) -> list[dict]:
        """List all skills with their status."""
        return [
            {
                "name": s.name,
                "version": s.version,
                "description": s.description,
                "enabled": s.enabled,
                "loaded": s.name in self.loaded_skills,
                "tags": s.tags,
            }
            for s in self.skills.values()
        ]

    def reload(self) -> None:
        """Reload the skill index from disk."""
        self.skills.clear()
        self._load_index()


# Global registry instance
_global_registry: Optional[SkillRegistry] = None


def get_skill_registry(skills_dir: Optional[Path] = None) -> SkillRegistry:
    """Get or create the global skill registry."""
    global _global_registry
    if _global_registry is None:
        if skills_dir is None:
            skills_dir = Path.home() / ".friday" / "skills"
        _global_registry = SkillRegistry(skills_dir)
    return _global_registry
