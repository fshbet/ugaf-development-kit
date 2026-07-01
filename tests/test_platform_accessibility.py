"""Tests for the accessibility abstraction contract.

No concrete adapter ships yet (see module docstring in
``ugaf/platform/accessibility.py``); these tests exercise the
dataclass and interface contract only.
"""

from __future__ import annotations

from ugaf.platform.accessibility import AccessibilityNode, AccessibilityProvider


class _FakeAccessibilityProvider(AccessibilityProvider):
    def __init__(self, available: bool, root: AccessibilityNode) -> None:
        self._available = available
        self._root = root

    def is_available(self) -> bool:
        return self._available

    def dump_hierarchy(self) -> AccessibilityNode:
        return self._root


def test_node_defaults_to_no_children() -> None:
    node = AccessibilityNode(
        node_class="android.widget.Button",
        text="OK",
        bounds=(0, 0, 100, 40),
        clickable=True,
    )
    assert node.children == []


def test_node_supports_nested_children() -> None:
    child = AccessibilityNode(
        node_class="android.widget.TextView",
        text="Label",
        bounds=(0, 0, 50, 20),
        clickable=False,
    )
    root = AccessibilityNode(
        node_class="android.widget.LinearLayout",
        text="",
        bounds=(0, 0, 100, 100),
        clickable=False,
        children=[child],
    )
    assert root.children == [child]


def test_provider_contract() -> None:
    root = AccessibilityNode(node_class="root", text="", bounds=(0, 0, 0, 0), clickable=False)
    provider = _FakeAccessibilityProvider(available=True, root=root)
    assert provider.is_available() is True
    assert provider.dump_hierarchy() == root
