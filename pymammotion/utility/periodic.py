import asyncio
from contextlib import suppress


class Periodic:
    def __init__(self, func, time) -> None:
        self.func = func
        self.time = time
        self.is_started = False
        self._task = None

    def start(self) -> None:
        """Start the task if it is not already started.

        If the task is not already started, it sets the 'is_started' flag to
        True and initiates a task to call a function periodically using asyncio.
        """

        if not self.is_started:
            self.is_started = True
            # Start task to call func periodically:
            self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        """Stop the task if it is currently running.

        If the task is currently running, it will be cancelled and awaited until
        it stops.
        """

        if self.is_started:
            self.is_started = False
            # Stop task and await it stopped:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        """Run the specified function at regular intervals using asyncio.

        This method runs the specified function at regular intervals based on
        the time provided.

        Args:
            self: The instance of the class.

        """

        while True:
            await asyncio.sleep(self.time)
            await self.func()


def periodic(period):
    """Schedule a function to run periodically at a specified time interval.

    This decorator function takes a period (in seconds) as input and returns
    a scheduler function. The scheduler function, when applied as a
    decorator to another function, will run the decorated function
    periodically at the specified time interval.

    Args:
        period (int): Time interval in seconds at which the decorated function should run
            periodically.

    Returns:
        function: A scheduler function that can be used as a decorator to run a function
            periodically.

    """

    def scheduler(fcn):
        """Schedule the execution of a given async function periodically.

        This function takes an async function as input and returns a new async
        function that will execute the input function periodically at a
        specified interval.

        Args:
            fcn (function): The async function to be scheduled.

        Returns:
            function: An async function that will execute the input function periodically.

        """

        async def wrapper(*args, **kwargs) -> None:
            """Execute the given function periodically using asyncio tasks.

            This function continuously creates an asyncio task to execute the
            provided function with the given arguments and keyword arguments. It
            then waits for a specified period of time before creating the next task.

            Args:
                *args: Variable length argument list to be passed to the function.
                **kwargs: Arbitrary keyword arguments to be passed to the function.

            """

            while True:
                asyncio.create_task(fcn(*args, **kwargs))
                await asyncio.sleep(period)

        return wrapper

    return scheduler
