from dataclasses import dataclass


@dataclass
class Credentials:
    email: str
    password: str
    account_id: str