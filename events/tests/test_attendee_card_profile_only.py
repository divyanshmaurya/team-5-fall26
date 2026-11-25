"""Attendee cards link to profiles; messaging starts on the profile (#191)."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ContactPermission, User
from events.models import (
    ContactRequest,
    Conversation,
    Event,
    EventInterest,
    Registration,
)


class AttendeeCardProfileOnlyTests(TestCase):
    """The hover card offers See Details only, for both attendee groups."""

    @classmethod
    def setUpTestData(cls):
        start = timezone.now() + timedelta(days=3)
        cls.event = Event.objects.create(
            guid="card-profile-only",
            title="Riverside Picnic",
            content_hash="c" * 64,
            start_time=start,
            end_time=start + timedelta(hours=2),
            status=Event.Status.UPCOMING,
        )
        cls.viewer = User.objects.create_user(
            "cardviewer", "cardviewer@example.com", share_profile_with_attendees=True
        )
        cls.interested = User.objects.create_user(
            "cardfan", "cardfan@example.com", share_profile_with_attendees=True
        )
        cls.registered = User.objects.create_user(
            "cardguest", "cardguest@example.com", share_profile_with_attendees=True
        )
        EventInterest.objects.create(event=cls.event, user=cls.viewer)
        EventInterest.objects.create(event=cls.event, user=cls.interested)
        Registration.objects.create(event=cls.event, user=cls.registered)

    def setUp(self):
        self.client.force_login(self.viewer)
        self.detail_url = reverse("event_detail", args=[self.event.pk])

    def card_actions(self, html, username):
        """Return the action area of the hover card for ``username``."""
        card = html[html.index(f"@{username}") :]
        card = card[card.index('class="attendee-card-actions"') :]
        return card[: card.index("</div>")]

    def test_interested_and_registered_cards_only_link_to_the_profile(self):
        """No messaging form in either group, just See Details."""
        html = self.client.get(self.detail_url).content.decode()

        for member in (self.interested, self.registered):
            with self.subTest(member=member.username):
                actions = self.card_actions(html, member.username)
                profile_url = reverse("public_profile", args=[member.username])
                self.assertIn(f'href="{profile_url}"', actions)
                self.assertIn("See Details", actions)
                self.assertNotIn("<form", actions)
                self.assertNotIn("<textarea", actions)
                self.assertNotIn("Contact", actions)

    def test_profile_shows_send_message_for_both_groups(self):
        """See Details leads to a profile with the Send Message button."""
        for member in (self.interested, self.registered):
            with self.subTest(member=member.username):
                page = self.client.get(
                    reverse("public_profile", args=[member.username])
                )
                self.assertContains(page, "Send Message")
                self.assertContains(page, reverse("message_user", args=[member.pk]))

    def test_open_contact_lets_people_message_directly(self):
        """Allow direct contact: sending opens the conversation straight away."""
        self.registered.contact_permission = ContactPermission.OPEN
        self.registered.save(update_fields=["contact_permission"])

        response = self.client.post(
            reverse("message_user", args=[self.registered.pk]),
            {"event": self.event.pk, "message": "Hi there"},
        )

        conversation = Conversation.objects.get()
        self.assertRedirects(
            response,
            reverse("conversation", args=[conversation.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            ContactRequest.objects.get().status, ContactRequest.Status.ACCEPTED
        )

    def test_approval_required_sends_a_request_to_accept_or_decline(self):
        """Require approval: sending creates a pending request, no chat yet."""
        self.interested.contact_permission = ContactPermission.APPROVAL_REQUIRED
        self.interested.save(update_fields=["contact_permission"])

        self.client.post(
            reverse("message_user", args=[self.interested.pk]),
            {"event": self.event.pk, "message": "Hi there"},
        )

        request = ContactRequest.objects.get()
        self.assertEqual(request.status, ContactRequest.Status.PENDING)
        self.assertFalse(Conversation.objects.exists())

        self.client.force_login(self.interested)
        self.client.post(
            reverse("respond_to_contact_request", args=[request.pk, "accept"])
        )
        request.refresh_from_db()
        self.assertEqual(request.status, ContactRequest.Status.ACCEPTED)
        response = self.client.get(reverse("message_user", args=[self.viewer.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Conversation.objects.exists())
