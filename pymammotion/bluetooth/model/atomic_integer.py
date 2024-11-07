from threading import Lock


class AtomicInteger:
    """Thread-safe atomic integer implementation."""

    def __init__(self, initial_value: int = 0) -> None:
        """Initialize atomic integer with given value."""
        self._value = initial_value
        self._lock = Lock()

    def get(self) -> int:
        """Get the current value."""
        with self._lock:
            return self._value

    def set(self, value: int) -> None:
        """Set a new value."""
        with self._lock:
            self._value = value

    def increment_and_get(self) -> int:
        """Increment the value and return the new value."""
        with self._lock:
            self._value += 1
            return self._value

    def decrement_and_get(self) -> int:
        """Decrement the value and return the new value."""
        with self._lock:
            self._value -= 1
            return self._value

    def add_and_get(self, delta: int) -> int:
        """Add delta to value and return the new value."""
        with self._lock:
            self._value += delta
            return self._value

    def compare_and_set(self, expect: int, update: int) -> bool:
        """Compare value with expected and set to update if they match."""
        with self._lock:
            if self._value == expect:
                self._value = update
                return True
            return False

    def __str__(self) -> str:
        """Returns string representation of the atomic integer."""
        return str(self.get())

    def __repr__(self) -> str:
        """Detailed string representation of the atomic integer."""
        return f"AtomicInteger({self.get()})"
