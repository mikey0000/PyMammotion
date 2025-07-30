from typing import TypeVar, Union, get_args, get_origin

from pymammotion.http.model.http import Response

T = TypeVar("T")


def deserialize_data(value, target_type):
    """Deserialize data into a specified target type.
    
    The function handles deserialization of basic types, lists, and unions. It
    recursively processes list elements and supports optional types by handling
    Union[T, None]. For custom types with a `from_dict` method, it calls this
    method for deserialization. If the target type is unknown or unsupported, it
    returns the value unchanged.
    
    Args:
        value: The data to be deserialized.
        target_type (type): The desired type into which the data should be deserialized.
    
    Returns:
        The deserialized data in the specified target type.
    """
    if value is None:
        return None

    origin = get_origin(target_type)
    args = get_args(target_type)

    if origin is list and args:
        item_type = args[0]
        return [deserialize_data(v, item_type) for v in value]

    if origin is Union:
        # Support Optional[T] = Union[T, None]
        non_none_types = [t for t in args if t is not type(None)]
        if len(non_none_types) == 1:
            return deserialize_data(value, non_none_types[0])

    if hasattr(target_type, "from_dict"):
        return target_type.from_dict(value)

    return value  # fallback: unknown type, leave as-is


def response_factory(response_cls: type[Response[T]], raw_dict: dict) -> Response[T]:
    # Extract the type of the generic `data` field
    """Create a Response instance from a dictionary."""
    data_type = get_args(response_cls)[0] if get_args(response_cls) else None

    if data_type:
        data_value = deserialize_data(raw_dict.get("data"), data_type)
        return Response(code=raw_dict["code"], msg=raw_dict["msg"], data=data_value)
    else:
        return response_cls.from_dict(raw_dict)
