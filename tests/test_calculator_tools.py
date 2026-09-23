from brainbox_os.calculator_tools import calculate_expression, parse_arithmetic_request


def test_calculate_expression_exact_integer_math():
    assert calculate_expression("27 * 14")["result"] == 378
    assert calculate_expression("38529 * 14")["result"] == 539406
    assert calculate_expression("(20 + 4) * 14")["result"] == 336


def test_parse_arithmetic_request_understands_voice_phrasing():
    result = parse_arithmetic_request("Open Calculator and calculate 24 multiplied by 14 and tell me the result")
    assert result == {"expression": "24 * 14", "open_calculator": True}


def test_parse_arithmetic_request_returns_none_for_non_arithmetic():
    assert parse_arithmetic_request("Open Calculator and type hello") is None
