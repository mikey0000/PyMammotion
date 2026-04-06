from functools import cache
from typing import TypeVar

from mashumaro.codecs import BasicDecoder

from pymammotion.http.model.http import Response

T = TypeVar("T")


@cache
def _decoder(response_cls: type) -> BasicDecoder:
    return BasicDecoder(response_cls)


def response_factory(response_cls: type[Response[T]], raw_dict: dict) -> Response[T]:
    """Create a Response instance from a dictionary, deserializing the generic data field."""
    return _decoder(response_cls).decode(raw_dict)
