from app.core.security import create_access_token


def test_access_token_is_created() -> None:
    token = create_access_token("admin@example.com")
    assert isinstance(token, str)
    assert token.count(".") == 2
