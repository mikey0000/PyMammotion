import asyncio
from contextlib import suppress


class Periodic:
    def __init__(self, func, time):
        self.func = func
        self.time = time
        self.is_started = False
        self._task = None

    def start(self):
        """Start the task if it is not already started.

        If the task is not already started, it sets the 'is_started' flag to
        True and starts a task to call the '_run' function periodically using
        asyncio.
        """

        if not self.is_started:
            self.is_started = True
            # Start task to call func periodically:
            self._task = asyncio.ensure_future(self._run())

    async def stop(self):
        """Stop the task if it is currently running.

        If the task is running, it will be cancelled and awaited until it stops.
        """

        if self.is_started:
            self.is_started = False
            # Stop task and await it stopped:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self):
        """Asynchronously runs the provided function at regular intervals.

        This method runs the provided function asynchronously at regular
        intervals specified by the 'time' attribute of the object.
        """

        while True:
            await asyncio.sleep(self.time)
            await self.func()


def periodic(period):
    """Decorator to schedule a function to run periodically at a specified
    interval.

    Args:
        period (int): The time interval in seconds at which the function should run
            periodically.

    Returns:
        function: A decorator function that schedules the decorated function to run
            periodically.
            Usage:
        async def my_periodic_function():
            # Code to be executed periodically

    Note:
        The decorated function will be scheduled to run in an infinite loop with
        the specified time interval.
    """

    def scheduler(fcn):
        """Schedule the execution of a given asynchronous function at regular
        intervals.

        This function takes an asynchronous function as input and schedules its
        execution at regular intervals.

        Args:
            fcn (function): An asynchronous function to be scheduled.

        Returns:
            function: A wrapper function that schedules the execution of the input function.
        """

        async def wrapper(*args, **kwargs):
            """Execute the given function periodically using asyncio tasks.

            This function continuously creates an asyncio task to execute the
            provided function with the given arguments and keyword arguments. It
            then waits for the specified period of time before creating the next
            task.

            Args:
                *args: Variable length argument list to be passed to the function.
                **kwargs: Arbitrary keyword arguments to be passed to the function.
            """

            while True:
                asyncio.create_task(fcn(*args, **kwargs))
                await asyncio.sleep(period)

        return wrapper

    return scheduler
