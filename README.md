# Stripe Traveller (python)

A significant part of Stripe's functionality is handled via lifecycle events, e.g. an invoice being generated when a subscription reaches the end of its billing cycle. There are two ways to test code that deals with these lifecycle events:

1. Create fixtures that replicate Stripe objects (e.g. `stripe.Subscription`) or events (e.g. `stripe.WebhookEvent`), then pass those fixtures to the end code.
2. Use Test Clocks to simulate the flow of time in a test environment and allow Stripe to trigger actual lifecycle events.

The former is great when you need/want to test locally and/or quickly. The latter is great when you want a simpler test framework and want to rely on Stripe to generate objects and events, at the expense of longer test cycles and the inability to receive webhook events locally.

This library is intended to be used as a test helper for the latter scenario.

## Working with Test Clocks

Test clocks can be difficult to work with directly, in part because you *must* ensure you are disposing of test clocks when your code ends, otherwise you could get stuck with a lot of junk resources in your Stripe test environment.

*Traveller can be used alongside `with` to ensure test clocks are always disposed when the code block is exited.*

Additionally, test clocks require you to pass in a set point in time to advance to and do not offer relative time advancement functions.

*The `t.advance` function allows for relative time advancement while `t.goto` allows for absolute time advancement.*

Finally, Stripe does not use `async` in their functions, meaning that you must call `clock.advance` and then manually monitor the test clock in a loop while waiting for advancement to complete.

*You can simply `await t.advance` or `await t.goto`.*

## Working with Traveller

The best way to use the `Traveller` helper class is to use `with Traveller()`.

```python
with Traveller() as t:
    customer = stripe.Customer.create(test_clock=t.clock_id, ...)
    subscription = stripe.Subscription.create(customer=customer.id, items=items, ..)
    await t.advance(days=1)
```

Because we use `with Traveller()`, we are guaranteed that our test clock will be disposed of no matter how this block termiantes. Whether we fail an `assert`, invoke `exit`, have an uncaught exception, it doesn't matter; `__exit__` will always get called and ensure our test clock is deleted.

Additionally, we can use relative or absolute time advancement functions via `advance` and `goto`, respectively.

Finally, we can simply `await` either of those functions to ensure that the following lines of code do not execute until the test clock has completed its advancement of time.
