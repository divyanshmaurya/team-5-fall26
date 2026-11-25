"""The public profile shows a short list of interested events by default."""

from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from events.models import Event, EventInterest


class InterestedEventsMixin:
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
                registration_url="https://example.com/register",
            )
            EventInterest.objects.create(event=event, user=self.member)
            events.append(event)
        return events

    def event_link(self, event):
        return f'href="{reverse("event_detail", args=[event.pk])}"'

    def setUp(self):
        self.client.force_login(self.viewer)


class InterestedEventsPreviewTests(InterestedEventsMixin, TestCase):
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


class InterestedEventsReviewTests(InterestedEventsMixin, TestCase):
    """Toggle links keep page state, and the list matches the home page rule."""

    def make_event(self, guid, **fields):
        defaults = {
            "title": guid.replace("-", " ").title(),
            "content_hash": "r" * 64,
            "start_time": timezone.now() + timedelta(days=1),
            "registration_url": "https://example.com/register",
        }
        defaults.update(fields)
        event = Event.objects.create(guid=guid, **defaults)
        EventInterest.objects.create(event=event, user=self.member)
        return event

    def test_toggle_links_keep_the_other_query_parameters(self):
        self.mark_interested(4)
        response = self.client.get(self.url, {"from_event": "12", "photo_page": "2"})
        self.assertContains(
            response,
            f'href="{self.url}?from_event=12&amp;photo_page=2&amp;interested=all'
            '#interested-events"',
        )
        response = self.client.get(
            self.url, {"from_event": "12", "interested": "all", "photo_page": "2"}
        )
        self.assertContains(
            response,
            f'href="{self.url}?from_event=12&amp;photo_page=2#interested-events"',
        )

    def test_preview_counts_in_the_database_and_fetches_only_three(self):
        self.mark_interested(5)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url)
        self.assertEqual(response.context["upcoming_event_count"], 5)
        interested = [
            query["sql"]
            for query in queries.captured_queries
            if "events_eventinterest" in query["sql"]
            and "events_registration" not in query["sql"]
            and query["sql"].startswith('SELECT "events_event"."id"')
        ]
        self.assertEqual(len(interested), 1)
        self.assertIn("LIMIT 3", interested[0])

    def test_in_progress_events_show_like_on_the_home_page(self):
        now = timezone.now()
        under_way = self.make_event(
            "under-way",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        unlisted = self.make_event("no-signup", registration_url="")
        finished = self.make_event(
            "finished",
            start_time=now - timedelta(days=1),
            status=Event.Status.DONE,
        )
        profile = self.client.get(self.url)
        self.assertContains(profile, self.event_link(under_way))
        self.assertNotContains(profile, self.event_link(unlisted))
        self.assertNotContains(profile, self.event_link(finished))
        home = self.client.get(reverse("landing"))
        self.assertEqual(
            [event.pk for event in home.context["events"]],
            [event.pk for event in profile.context["shown_upcoming_events"]],
        )
