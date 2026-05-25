from kitchenpal.ui.errors import user_error_message


def test_user_error_message_adds_action_context():
    message = user_error_message(ValueError("No available purchase rows"), "Could not add purchase")

    assert message == "Could not add purchase: No available purchase rows"


def test_user_error_message_handles_empty_exception_text():
    message = user_error_message(ValueError(), "Could not update transfer")

    assert message == "Could not update transfer: The spreadsheet did not accept the update."
