from dataclasses import dataclass


@dataclass
class Credentials:
    email: str = None
    password: str = None
    account_id: str = None
