from brainbox_os.task_response import response_for_execution


def test_open_app_response_is_natural():
    assert response_for_execution([{"name": "open_application", "result": {"opened": True, "name": "Chrome"}}]) == "Done bro, Chrome is open."
