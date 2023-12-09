# This module assists with the use of Stripe Test Clocks.
#
# Test Clocks are a mechanism for artificially advancing time to test changes to an object's lifecycle.
#
# Example:
#
# ```python
# with Traveller() as t:
#     customer = stripe.Customer.create(test_clock=t.clock_id, ...)
#     subscription = stripe.Subscription.create(customer=customer.id, items=items, ..)
#     await t.advance(days=1)
# ```
#
# The above code will create a test clock, which is used to then create a customer.
#
# Customers are what associate with a test clock. Any subscriptions attached to that customer will then be affected by advacing the clock.
#
# It is important to note that time can only move *forward*, there is no going backward. Entering a negative value for any of the time units will result in an error.
#
# Because test clocks take a while to advance and run all necessary lifecycle events, you *must* `await` the `advance` method or you could end up taking actions before any state has changed.

from asyncio import sleep
from datetime import datetime, timedelta
from typing import Optional

from stripe import test_helpers


class Traveller:
    __slots__ = ("now", "clock")

    def __init__(self):
        self.now: datetime
        self.clock: test_helpers.TestClock

    # Simple way to get the timestamp of the "current" time, according to the test clock.
    @property
    def timestamp(self) -> int:
        return int(self.now.timestamp())

    # "Freeze" the current time and generate a test clock with it.
    def __enter__(self):
        self.now = datetime.now()
        self.clock = test_helpers.TestClock.create(frozen_time=self.timestamp)
        return self

    # Delete the test clock, which will also delete any associated customers and their associated resources (e.g. subscriptions, payment methods).
    def __exit__(self, exc_type, exc_value, traceback):
        test_helpers.TestClock.delete(self.clock.id)

    # Asynchronously advance the test clock by an amount of time relative to the current frozen time. Because Stripe's test clocks may cause many side effects, this function could take many seconds to complete.
    #
    # Note: Advancing in terms of months assumes 30 days per month. This is due to the limitations of Python's `timedelta` module.
    async def advance(
        self,
        months: Optional[int] = None,
        weeks: Optional[int] = None,
        days: Optional[int] = None,
        hours: Optional[int] = None,
    ):
        target = self.now

        # Convert the time units into a timedelta and add it to the "current" time.
        if months is not None:
            if months < 0:
                raise ValueError("Time cannot move backwards")
            target += timedelta(days=months * 30)
        if weeks is not None:
            if weeks < 0:
                raise ValueError("Time cannot move backwards")
            target += timedelta(weeks=weeks)
        if days is not None:
            if days < 0:
                raise ValueError("Time cannot move backwards")
            target += timedelta(days=days)
        if hours is not None:
            if hours < 0:
                raise ValueError("Time cannot move backwards")
            target += timedelta(hours=hours)

        # If no time was given, do nothing
        if target == self.now:
            return self

        return await self.goto(target)

    # Asynchronously advance the test clock to an absolute future point in time. Because Stripe's test clocks may cause many side effects, this function could take many seconds to complete.
    async def goto(self, time: datetime):
        if time < self.now:
            raise ValueError("Time cannot move backwards")

        self.now = time

        self.clock = test_helpers.TestClock.advance(
            self.clock.id, frozen_time=self.timestamp
        )
        while self.clock.status == "advancing":
            await sleep(1)
            self.clock = test_helpers.TestClock.retrieve(self.clock.id)

        if self.clock.status != "ready":
            raise Exception("Clock is not ready, something went wrong.")

        return self

    # Because some actions may be executed asynchronously (e.g. via webhooks), you might want to wait for a resource to fulfill some arbitrary condition before continuing.
    #
    # - `resource`: the Stripe object waiting to be updated.
    # - `predicate`: a function that takes one argument, the `resource`, and returns a boolean. If the predicate returns true, the wait is over.
    # - `timeout`: the maximum amount of time to wait before raising a TimeoutError. Defaults to 300 seconds (5 minutes).
    #
    # If successful, this returns the version of `resource` fetched from the API which caused the predicate to return true.
    #
    # *Important*: This function is not intended to validate whether a specific series of actions was taken against a resource, only whether the resource has changed or not. If the predicate does not return true within the given timeout period, a TimeoutError will be raised. It is better to use this function to wait for a clear signal that a state change of some kind has occurred, then take the resulting updated resource and validate that it is in the desired state.
    #
    # For example:
    #
    # ```python
    # # Wait for the subscription to be cancelled.
    # subscription = await t.wait_for(subscription, lambda s: s.status == "canceled")
    #
    # # Ensure the latest invoice was refunded.
    # invoice = stripe.Invoice.retrieve(subscription.latest_invoice)
    # assert has_full_refund(invoice)
    # ```
    #
    # In the above example, we are not waiting for the invoice to be refunded, we are waiting for the subscription to change it's state to the `canceled` status. Once that happens, we expect that the invoice should be refunded, so we can then retrieve the invoice and validate that it was refunded.
    async def wait_for(
        self,
        resource,
        predicate,
        timeout: int = 300,
    ) -> object:
        if timeout < 0:
            raise ValueError("Timeout cannot be negative")

        start = datetime.now().timestamp()
        while not predicate(resource):
            if datetime.now().timestamp() - start > timeout:
                raise TimeoutError(
                    f"Predicate did not return true within {timeout} seconds"
                )
            await sleep(1)
            resource = type(resource).retrieve(resource.id)

        return resource

    # This is a convenience method for waiting for a resource to reach a specific status. Will raise an error if `resource` does not have the `status` attribute.
    async def wait_for_status(
        self,
        resource,
        target_status: str,
        timeout: int = 300,
    ) -> object:
        return await self.wait_for(
            resource,
            lambda r: r.status == target_status,
            timeout,
        )
