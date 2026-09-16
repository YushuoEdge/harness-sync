import pytest

from harness_sync.errors import ConflictError
from harness_sync.merge import MISSING, merge_fields


def test_three_way_merge_preserves_unowned_fields_and_removes_owned_leaf():
    baseline = {"provider": {"model": "old", "effort": "high"}, "user": 1}
    current = {"provider": {"model": "old", "effort": "high"}, "user": 2}
    result = merge_fields(
        current,
        baseline,
        {
            ("provider", "model"): "new",
            ("provider", "effort"): MISSING,
        },
    )
    assert result == {"provider": {"model": "new"}, "user": 2}
    assert current["provider"]["effort"] == "high"


def test_same_as_desired_external_edit_is_not_a_conflict():
    assert merge_fields({"model": "new"}, {"model": "old"}, {("model",): "new"}) == {
        "model": "new",
    }


def test_parent_type_change_cannot_destroy_user_data():
    with pytest.raises(ConflictError):
        merge_fields({"provider": "user-value"}, None, {("provider", "model"): "new"})


def test_overlapping_field_paths_rejected():
    with pytest.raises(ConflictError):
        merge_fields({}, None, {("provider",): {}, ("provider", "model"): "new"})
