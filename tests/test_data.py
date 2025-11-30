from human_eval import data


def test_stream_jsonl_valid(tmp_path):
    file = tmp_path / "sample.jsonl"
    file.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    rows = list(data.stream_jsonl(str(file)))
    assert rows == [{"a": 1}, {"b": 2}]


def test_get_human_eval_dataset_rejects_other_language():
    try:
        data.get_human_eval_dataset("python")
    except ValueError:
        assert True
    else:
        raise AssertionError("expected ValueError")
