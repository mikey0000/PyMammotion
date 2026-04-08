from dataclasses import dataclass


@dataclass
class Credentials:
    """User login credentials for authenticating with the Mammotion cloud."""

    email: str = None
    password: str = None
    account_id: str = None
