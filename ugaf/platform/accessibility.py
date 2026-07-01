"""Accessibility-tree abstraction.

No concrete adapter ships in Milestone 2. Android's Accessibility
Service is one of several candidate transports evaluated in Milestone
4 (Android Transport) alongside UIAutomator2/Scrcpy/ADB — which one
backs this interface on Android is a decision for that milestone, not
this one. Windows' equivalent (UI Automation / MSAA) would require a
new third-party dependency (``pywinauto`` or ``comtypes``) and is
deferred until a concrete need justifies adding it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

__all__ = [
    "AccessibilityNode",
    "AccessibilityProvider",
]


@dataclass(frozen=True)
class AccessibilityNode:
    """A single node in an accessibility tree snapshot.

    Attributes:
        node_class: Platform-specific element type (e.g. Android's
            ``className``, such as ``"android.widget.Button"``).
        text: Visible text content, if any.
        bounds: Bounding box as ``(left, top, right, bottom)`` in
            screen pixels.
        clickable: Whether the platform reports this node as
            interactive.
        children: Nested child nodes.

    """

    node_class: str
    text: str
    bounds: tuple[int, int, int, int]
    clickable: bool
    children: list[AccessibilityNode] = field(default_factory=list)


class AccessibilityProvider(ABC):
    """Abstract interface for reading a platform's accessibility tree.

    Deliberately narrow (read-only tree access) — accessibility-driven
    *interaction* (tapping a node found here) is expected to go back
    through :class:`ugaf.input.provider.InputProvider` using the
    node's ``bounds``, not through this interface, to avoid a second
    parallel input path.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether the accessibility service is currently reachable."""

    @abstractmethod
    def dump_hierarchy(self) -> AccessibilityNode:
        """Return the current accessibility tree, rooted at the top-level window.

        Raises:
            AdapterNotAvailableError: If the accessibility service is
                not available (see :meth:`is_available`).

        """
