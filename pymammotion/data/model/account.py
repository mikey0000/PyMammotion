from dataclasses import dataclass


@dataclass
class Credentials:
    """User login credentials for authenticating with the Mammotion cloud."""

    email: str | None = None
    password: str | None = None
    account_id: str | None = None
