from django.test import SimpleTestCase

from apps.common.events import DomainEvent, clear_subscribers, publish, subscribe


class EventBusTests(SimpleTestCase):
    def tearDown(self):
        clear_subscribers()

    def test_delivers_to_subscribers(self):
        seen = []
        subscribe("demo.happened", seen.append)
        publish(DomainEvent(name="demo.happened", payload={"a": 1}))
        self.assertEqual(seen[0].payload, {"a": 1})

    def test_failing_subscriber_does_not_block_others(self):
        seen = []

        def boom(event):
            raise RuntimeError("subscriber is broken")

        subscribe("demo.happened", boom)
        subscribe("demo.happened", seen.append)

        with self.assertLogs("apps.common.events", level="ERROR"):
            publish(DomainEvent(name="demo.happened"))

        self.assertEqual(len(seen), 1)

    def test_unknown_event_is_a_noop(self):
        publish(DomainEvent(name="nobody.listens"))
