from src.management_flags.candidate_rules import Candidate
from src.management_flags.materiality import rank_and_select

def test_four_is_a_cap_not_a_target():
    candidates = [
        Candidate("arr_growth","growth","positive",["arr_yoy_growth_pct"],{},95,family="growth"),
        Candidate("nrr","retention","positive",["nrr_12m"],{},88,family="nrr"),
    ]
    assert len(rank_and_select(candidates, minimum_score=60, max_flags=4)) == 2

def test_below_threshold_is_dropped():
    candidates = [Candidate("minor","growth","positive",["arr_yoy_growth_pct"],{},40)]
    assert rank_and_select(candidates, minimum_score=60, max_flags=4) == []
