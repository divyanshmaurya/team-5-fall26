"""Signed-out visitors see upcoming events on the home page (#205)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event, Registration
from events.views import UPCOMING_EVENT_LIMIT


def make_event(guid, title, days, status=Event.Status.UPCOMING):
    """Create a listed feed event starting ``days`` from now."""
    start = timezone.now() + timedelta(days=days)
    return Event.objects.create(
        guid=guid,
        title=title,
        content_hash="",
        start_time=start,
        end_time=start + timedelta(hours=2),
        status=status,
        registration_url="https://example.com/register",
    )


class VisitorUpcomingEventsTests(TestCase):
    """The Upcoming events section is shown whether or not you're signed in."""

    @classmethod
    def setUpTestData(cls):
        cls.later = make_event("v-later", "Later Harbor Walk", 5)
        cls.sooner = make_event("v-sooner", "Sooner Garden Day", 2)
        cls.done = make_event("v-done", "Finished Cleanup", -3, Event.Status.DONE)
        cls.user = get_user_model().objects.create_user(
            "visitorcheck", "visitorcheck@example.com", "pass12345"
        )

    def home(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        return response

    def test_signed_out_visitors_see_upcoming_events_soonest_first(self):
        """Cards appear in date order with the View all link."""
        response = self.home()

        self.assertEqual(list(response.context["events"]), [self.sooner, self.later])
        self.assertContains(response, 'id="events-heading"')
        self.assertContains(response, "View all upcoming events")
        self.assertContains(response, "Sooner Garden Day")

    def test_sign_up_card_comes_before_upcoming_events(self):
        """Visitors still get the join card, above the events."""
        html = self.home().content.decode()

        self.assertLess(
            html.index('class="join-card"'), html.index('id="events-heading"')
        )

    def test_signed_out_visitors_get_no_personal_sections(self):
        """No recommendations or archive, and no archived events listed."""
        response = self.home()

        self.assertNotContains(response, 'id="recommendations-heading"')
        self.assertNotContains(response, 'id="archived-heading"')
        self.assertNotContains(response, "Finished Cleanup")

    def test_card_actions_send_visitors_to_log_in(self):
        """A hosted event's card asks visitors to log in, then come back."""
        start = timezone.now() + timedelta(days=1)
        Event.objects.create(
            guid=Event.HOSTED_GUID_PREFIX + "visitor-hosted",
            title="Hosted Picnic",
            content_hash="",
            start_time=start,
            end_time=start + timedelta(hours=2),
            host=self.user,
        )

        response = self.home()

        self.assertContains(response, "Hosted Picnic")
        html = response.content.decode()
        button = html[: html.index("Log in to Register")]
        button = button[button.rindex("<a") :]
        self.assertIn(f'href="{reverse("login")}?next=/"', button)
        self.assertNotContains(response, "You are registered for this event")

    def test_visitor_list_is_capped_like_the_signed_in_list(self):
        """At most the same number of upcoming events as for members."""
        for i in range(UPCOMING_EVENT_LIMIT + 3):
            make_event(f"v-extra-{i}", f"Extra Walk {i}", 10 + i)

        self.assertEqual(len(self.home().context["events"]), UPCOMING_EVENT_LIMIT)

    def test_signed_in_home_is_unchanged(self):
        """Members still see upcoming and archived events, without the join card."""
        Registration.objects.create(event=self.sooner, user=self.user, party_size=1)
        self.client.force_login(self.user)

        response = self.home()

        self.assertNotContains(response, 'class="join-card"')
        self.assertContains(response, 'id="events-heading"')
        self.assertContains(response, 'id="archived-heading"')
        self.assertContains(response, "Finished Cleanup")
