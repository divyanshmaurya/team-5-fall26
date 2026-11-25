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

    def visitor_actions(self, html, event):
        """Return the signed-out action block on ``event``'s home card."""
        card = html[html.index(f'href="{reverse("event_detail", args=[event.pk])}"') :]
        card = card[card.index('class="visitor-actions"') :]
        return card[: card.index("</div>")]

    def login_url_for(self, event):
        """The login link that returns the visitor to ``event``."""
        event_url = reverse("event_detail", args=[event.pk])
        return f'href="{reverse("login")}?next={event_url}"'

    def test_card_actions_send_visitors_to_log_in_and_back_to_the_event(self):
        """Register, Interested and Favorite all log in, then open the event.

        Covers both card types: a hosted event and a feed event that has its
        own registration page.
        """
        start = timezone.now() + timedelta(days=1)
        hosted = Event.objects.create(
            guid=Event.HOSTED_GUID_PREFIX + "visitor-hosted",
            title="Hosted Picnic",
            content_hash="",
            start_time=start,
            end_time=start + timedelta(hours=2),
            host=self.user,
        )

        html = self.home().content.decode()

        for event in (hosted, self.sooner):
            with self.subTest(event=event.title):
                actions = self.visitor_actions(html, event)
                self.assertEqual(actions.count(self.login_url_for(event)), 3)
                self.assertIn("Log in to Register", actions)
                self.assertIn("Mark Interested", actions)
                self.assertIn("Add to Favorites", actions)
                self.assertNotIn("example.com/register", actions)
        self.assertNotIn("External Register", html)
        self.assertNotIn("You are registered for this event", html)

    def test_ended_events_get_no_visitor_actions(self):
        """Only open events offer the log-in actions."""
        self.sooner.end_time = timezone.now() - timedelta(minutes=1)
        self.sooner.start_time = self.sooner.end_time - timedelta(hours=2)
        self.sooner.save()

        html = self.home().content.decode()

        self.assertEqual(html.count('class="visitor-actions"'), 1)
        self.assertNotIn(self.login_url_for(self.sooner), html)

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
        self.assertNotContains(response, 'class="visitor-actions"')
        self.assertContains(response, 'id="events-heading"')
        self.assertContains(response, 'id="archived-heading"')
        self.assertContains(response, "Finished Cleanup")
