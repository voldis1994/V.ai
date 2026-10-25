"""50 aģentu reģistrs."""

from .catalog import AGENT_DEFINITIONS, get_agent, list_agents, list_sections, validate_registry

__all__ = [
    "AGENT_DEFINITIONS",
    "get_agent",
    "list_agents",
    "list_sections",
    "validate_registry",
]
