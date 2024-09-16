import betterproto


def has_field(message: betterproto.Message) -> bool:
    """Check if the message has any fields serialized on wire."""
    return betterproto.serialized_on_wire(message)