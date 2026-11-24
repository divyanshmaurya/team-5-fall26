"""The public profile shows a short list of interested events by default."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from events.models import Event, EventInterest


class InterestedEventsPreviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(
            "planner", "planner@example.com", share_profile_with_attendees=True
        )
        cls.viewer = User.objects.create_user("viewer", "viewer@example.com")
        cls.url = reverse("public_profile", args=[cls.member.username])
        cls.all_url = f"{cls.url}?interested=all#interested-events"

    def mark_interested(self, count):
        events = []
        for day in range(1, count + 1):
            event = Event.objects.create(
                guid=f"interest-{day}",
                title=f"Park event {day}",
                content_hash="i" * 64,
                start_time=timezone.now() + timedelta(days=day),
            )
            EventInterest.objects.create(event=event, user=self.member)
            events.append(event)
        return events

    def event_link(self, event):
        return f'href="{reverse("event_detail", args=[event.pk])}"'

    def setUp(self):
        self.client.force_login(self.viewer)

    def test_only_the_three_soonest_events_show_by_default(self):
        events = self.mark_interested(5)
        response = self.client.get(self.url)
        for event in events[:3]:
            self.assertContains(response, self.event_link(event))
        for event in events[3:]:
            self.assertNotContains(response, self.event_link(event))
        self.assertContains(response, "5 events")
        self.assertContains(response, f'href="{self.all_url}"')
        self.assertContains(response, "Show all 5 interested events")

    def test_show_all_link_lists_every_interested_event(self):
        events = self.mark_interested(5)
        response = self.client.get(self.url, {"interested": "all"})
        for event in events:
            self.assertContains(response, self.event_link(event))
        self.assertNotContains(response, "Show all 5 interested events")
        self.assertContains(response, f'href="{self.url}#interested-events"')
        self.assertContains(response, "Show fewer events")

    def test_three_or_fewer_events_need_no_show_all_link(self):
        for count in (0, 3):
            with self.subTest(count=count):
                EventInterest.objects.all().delete()
                Event.objects.all().delete()
                events = self.mark_interested(count)
                response = self.client.get(self.url)
                for event in events:
                    self.assertContains(response, self.event_link(event))
                self.assertNotContains(response, "interested=all")
                self.assertNotContains(response, "Show fewer events")

    def test_unknown_values_keep_the_short_list(self):
        events = self.mark_interested(4)
        response = self.client.get(self.url, {"interested": "everything"})
        self.assertNotContains(response, self.event_link(events[3]))
        self.assertContains(response, "Show all 4 interested events")
