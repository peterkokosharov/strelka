# Copyright (c) 2026 Peter Kokosharov <peter.kokosharov@gmail.com>
# SPDX-License-Identifier: MIT
# AI models: claude-opus-4-8
"""Geometry tests."""

from py_tvision.geometry import Point, Rect


def test_rect_size_and_origin():
    r = Rect.from_size(3, 4, 10, 5)
    assert r.width == 10
    assert r.height == 5
    assert r.origin == Point(3, 4)
    assert r.x2 == 13 and r.y2 == 9


def test_contains_is_half_open():
    r = Rect(0, 0, 4, 3)
    assert r.contains(Point(0, 0))
    assert r.contains(Point(3, 2))
    assert not r.contains(Point(4, 2))  # x2 excluded
    assert not r.contains(Point(3, 3))  # y2 excluded


def test_intersect():
    a = Rect(0, 0, 10, 10)
    b = Rect(5, 5, 20, 20)
    assert a.intersect(b) == Rect(5, 5, 10, 10)
    assert a.intersect(Rect(20, 20, 30, 30)).is_empty()


def test_union_and_empty():
    a = Rect(0, 0, 2, 2)
    b = Rect(5, 5, 7, 7)
    assert a.union(b) == Rect(0, 0, 7, 7)
    empty = Rect(0, 0, 0, 0)
    assert empty.is_empty()
    assert a.union(empty) == a


def test_move_and_grow():
    r = Rect(2, 2, 6, 6)
    assert r.move(1, -1) == Rect(3, 1, 7, 5)
    assert r.grow(1, 1) == Rect(1, 1, 7, 7)


def test_point_arithmetic():
    assert Point(1, 2) + Point(3, 4) == Point(4, 6)
    assert Point(5, 5) - Point(2, 1) == Point(3, 4)
