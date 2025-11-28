import numpy as np

from human_eval.evaluation import estimate_pass_at_k


def test_pass_at_k_edge_cases():
    total = [1, 2]
    correct = [1, 0]
    result = estimate_pass_at_k(total, correct, 1)
    assert np.isclose(result[0], 1.0)
    assert result[1] >= 0.0
