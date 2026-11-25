# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Points and rectangles.

A ``Rect`` is half-open: it covers columns ``x`` in ``[x1, x2)`` and rows
``y`` in ``[y1, y2)``, so ``width == x2 - x1``. This matches how views lay
out their children and how the clip code tests membership.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: int = 0
    y: int = 0

    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Point") -> "Point":
        return Point(self.x - other.x, self.y - other.y)


@dataclass(frozen=True)
class Rect:
    x1: int = 0
    y1: int = 0
    x2: int = 0
    y2: int = 0

    @classmethod
    def from_size(cls, x: int, y: int, width: int, height: int) -> "Rect":
        return cls(x, y, x + width, y + height)

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def origin(self) -> Point:
        return Point(self.x1, self.y1)

    def is_empty(self) -> bool:
        return self.x2 <= self.x1 or self.y2 <= self.y1

    def move(self, dx: int, dy: int) -> "Rect":
        return Rect(self.x1 + dx, self.y1 + dy, self.x2 + dx, self.y2 + dy)

    def grow(self, dx: int, dy: int) -> "Rect":
        """Grow (or shrink, for negative deltas) on every side."""
        return Rect(self.x1 - dx, self.y1 - dy, self.x2 + dx, self.y2 + dy)

    def intersect(self, other: "Rect") -> "Rect":
        return Rect(
            max(self.x1, other.x1),
            max(self.y1, other.y1),
            min(self.x2, other.x2),
            min(self.y2, other.y2),
        )

    def union(self, other: "Rect") -> "Rect":
        if self.is_empty():
            return other
        if other.is_empty():
            return self
        return Rect(
            min(self.x1, other.x1),
            min(self.y1, other.y1),
            max(self.x2, other.x2),
            max(self.y2, other.y2),
        )

    def contains(self, p: Point) -> bool:
        return self.x1 <= p.x < self.x2 and self.y1 <= p.y < self.y2

    def contains_xy(self, x: int, y: int) -> bool:
        return self.x1 <= x < self.x2 and self.y1 <= y < self.y2
