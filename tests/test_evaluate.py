"""Scoring drafts against a people-made grouping (extended B-cubed)."""

from __future__ import annotations

from atg.analysis.evaluate import bcubed, compare


def test_identical_groupings_score_one() -> None:
    g = {"a": {"1", "2"}, "b": {"3"}}
    assert bcubed(g, g) == {"precision": 1.0, "recall": 1.0, "f": 1.0}


def test_merge_costs_precision_and_split_costs_recall() -> None:
    truth = {"claim": {"1", "2"}, "pay": {"3", "4"}}
    merged = {"all": {"1", "2", "3", "4"}}
    split = {"x": {"1"}, "y": {"2"}, "z": {"3", "4"}}
    assert bcubed(merged, truth)["precision"] == 0.5 and bcubed(merged, truth)["recall"] == 1.0
    assert bcubed(split, truth)["precision"] == 1.0 and bcubed(split, truth)["recall"] == 0.75
    out = compare(split, {**truth, "api": {"9"}}, decisions=2)
    assert out["oversplit"] == ["claim"] and out["overmerged"] == []
    assert out["reference_doors_not_in_map"] == ["9"] and out["correction_effort"] == 2


def test_auto_accepted_drafts_are_scored_on_their_own() -> None:
    truth = {"claim": {"1", "2"}, "pay": {"3", "4"}}
    found = {"a": {"1", "2"}, "b": {"3"}, "c": {"4", "9"}}
    out = compare(found, truth, auto={"a", "b", "c"})["auto_accepted"]
    assert out == {"total": 3, "equal_to_a_reference_feature": 1, "inside_one_reference_feature": 2}


def test_a_door_in_two_reference_features() -> None:
    truth = {"claim": {"1", "2"}, "review": {"2", "3"}}
    found = {"one": {"1", "2", "3"}}
    s = bcubed(found, truth)
    assert 0 < s["precision"] < 1 and 0 < s["recall"] < 1  # door 2's double membership is lost
