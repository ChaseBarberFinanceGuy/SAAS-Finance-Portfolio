import pytest
from src.management_flags.validator import ManagementFlagValidationError, validate_response

def test_zero_flags_is_valid():
    assert validate_response({"flags":[]}, selected_candidates=[], known_metric_ids={"current_arr"},
                             as_of_month="2026-06", filters={})

def test_unknown_metric_rejected():
    response = {"flags":[{"category":"growth","source_metrics":["made_up_metric"]}]}
    with pytest.raises(ManagementFlagValidationError):
        validate_response(response, selected_candidates=[{"category":"growth"}],
                          known_metric_ids={"current_arr"}, as_of_month="2026-06", filters={})
