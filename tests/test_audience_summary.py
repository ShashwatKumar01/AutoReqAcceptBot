from app.services.broadcast_targets import format_audience_lines


def test_format_audience_lines_eligible_only():
    text = format_audience_lines({"eligible": 5, "tracked": 5})
    assert "Broadcast eligible: <b>5</b>" in text
    assert "Tracked" not in text


def test_format_audience_lines_with_gap():
    text = format_audience_lines({"eligible": 3, "tracked": 10})
    assert "Broadcast eligible: <b>3</b>" in text
    assert "Tracked in bot DB: <b>10</b>" in text
    assert "7 have not" in text
