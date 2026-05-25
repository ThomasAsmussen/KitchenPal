def user_error_message(exc: Exception, action: str | None = None) -> str:
    detail = str(exc).strip() or "The spreadsheet did not accept the update."
    if action:
        return f"{action}: {detail}"
    return detail


def show_user_error(st, exc: Exception, action: str | None = None):
    st.error(user_error_message(exc, action))
