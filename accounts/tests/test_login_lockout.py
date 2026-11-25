"""The login lockout can't be dodged by retyping the account differently (#180)."""

import time

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.views import LOCKOUT_THRESHOLD, CustomLoginView

PASSWORD = "Tr1cky-Passphrase!"
OTHER_PASSWORD = "An0ther-Passphrase!"


class LockoutBypassTests(TestCase):
    """Failed attempts count against the account, however it is typed."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("alice", "alice@example.com", PASSWORD)

    def setUp(self):
        cache.clear()
        self.url = reverse("login")

    def fail_login(self, identifier, times=1):
        """Submit a wrong password ``times`` times using ``identifier``."""
        for _ in range(times):
            self.client.post(self.url, {"username": identifier, "password": "wrong"})

    def log_in(self, identifier):
        """Try the correct password and return whether a session was created."""
        self.client.post(self.url, {"username": identifier, "password": PASSWORD})
        return SESSION_KEY in self.client.session

    def test_other_capitalization_stays_locked(self):
        """Five failures lock the account for every capitalization of the email."""
        self.fail_login("alice@example.com", LOCKOUT_THRESHOLD)

        for spelling in ("ALICE@EXAMPLE.COM", "Alice@Example.com", "alice@example.com"):
            with self.subTest(spelling=spelling):
                self.assertFalse(self.log_in(spelling))

    def test_username_and_email_share_one_counter(self):
        """Failures spread across the username and email still add up."""
        self.fail_login("alice", 2)
        self.fail_login("ALICE", 1)
        self.fail_login("Alice@Example.com", 2)

        self.assertFalse(self.log_in("alice"))
        response = self.client.post(self.url, {"username": "alice", "password": "x"})
        self.assertIsNotNone(response.context["lock_expiry"])

    def test_remaining_attempts_count_every_spelling(self):
        """The warning reflects failures made with other spellings."""
        self.fail_login("alice")
        response = self.client.post(
            self.url, {"username": "ALICE@example.com", "password": "wrong"}
        )

        self.assertEqual(response.context["remaining_attempts"], LOCKOUT_THRESHOLD - 2)

    def test_success_with_any_spelling_clears_the_counter(self):
        """A correct login resets failures recorded under another spelling."""
        self.fail_login("ALICE", LOCKOUT_THRESHOLD - 1)
        self.assertTrue(self.log_in("alice@example.com"))
        self.client.logout()

        self.fail_login("alice")
        response = self.client.post(self.url, {"username": "alice", "password": "x"})
        self.assertEqual(response.context["remaining_attempts"], LOCKOUT_THRESHOLD - 2)

    def test_unknown_identifiers_are_counted_case_insensitively(self):
        """Text matching no account still shares one counter across case."""
        self.fail_login("nobody@example.com", LOCKOUT_THRESHOLD - 1)
        response = self.client.post(
            self.url, {"username": "NOBODY@example.com", "password": "wrong"}
        )

        self.assertIsNotNone(response.context["lock_expiry"])

    def test_cache_keys_have_a_fixed_safe_length(self):
        """Any typed text, however long or unusual, maps to a short key."""
        key = CustomLoginView()._get_attempt_key("login:" + "é <>" * 500)

        self.assertLess(len(key), 100)
        self.assertNotIn(" ", key)


class SharedIdentifierTests(TestCase):
    """One login text can match a username and another user's email."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        # A different account whose username is Alice's email address.
        cls.other = User.objects.create_user(
            "alice@example.com", "other@example.com", OTHER_PASSWORD
        )

    def setUp(self):
        cache.clear()
        self.url = reverse("login")

    def post(self, password, identifier="alice@example.com"):
        return self.client.post(
            self.url, {"username": identifier, "password": password}
        )

    def logged_in_as(self):
        return self.client.session.get(SESSION_KEY)

    def lock_alice(self):
        """Lock Alice's account by failing with her username."""
        for _ in range(LOCKOUT_THRESHOLD):
            self.client.post(self.url, {"username": "alice", "password": "wrong"})

    def test_other_account_logging_in_keeps_alices_failures(self):
        """Signing in to the other account doesn't clear Alice's counter."""
        for _ in range(LOCKOUT_THRESHOLD - 1):
            self.client.post(self.url, {"username": "alice", "password": "wrong"})

        self.post(OTHER_PASSWORD)
        self.assertEqual(self.logged_in_as(), str(self.other.pk))
        self.client.logout()

        response = self.client.post(
            self.url, {"username": "alice", "password": "wrong"}
        )
        self.assertIsNotNone(response.context["lock_expiry"])

    def test_locked_account_doesnt_block_the_other_account(self):
        """With Alice locked, the other account still logs in."""
        self.lock_alice()

        response = self.post(OTHER_PASSWORD)

        self.assertEqual(self.logged_in_as(), str(self.other.pk))
        self.assertRedirects(
            response, reverse("landing"), fetch_redirect_response=False
        )

    def test_locked_account_password_is_not_checked(self):
        """Alice's right password via the shared text gets the same answer as a
        wrong one, so the lock can't be used to guess it."""
        self.lock_alice()

        right = self.post(PASSWORD)
        self.assertIsNone(self.logged_in_as())
        wrong = self.post("still-wrong")

        self.assertEqual(right.status_code, wrong.status_code)
        self.assertEqual(right.context["form"].errors, wrong.context["form"].errors)
        self.assertIsNone(right.context["lock_expiry"])
        self.assertEqual(
            right.context["remaining_attempts"] - 1,
            wrong.context["remaining_attempts"],
        )

    def test_alice_stays_locked_by_her_own_username(self):
        """The lock still holds when Alice's own username is typed."""
        self.lock_alice()

        response = self.client.post(
            self.url, {"username": "alice", "password": PASSWORD}
        )

        self.assertIsNone(self.logged_in_as())
        self.assertIsNotNone(response.context["lock_expiry"])

    def test_both_accounts_locked_blocks_the_shared_text(self):
        """When every matching account is locked, the shared text is locked."""
        self.lock_alice()
        for _ in range(LOCKOUT_THRESHOLD):
            self.post("wrong")

        response = self.post(OTHER_PASSWORD)

        self.assertIsNone(self.logged_in_as())
        self.assertIsNotNone(response.context["lock_expiry"])

    def lock_other(self):
        """Lock the other account by failing with its own email."""
        for _ in range(LOCKOUT_THRESHOLD):
            self.client.post(
                self.url, {"username": "other@example.com", "password": "wrong"}
            )

    def test_locked_username_owner_cant_log_in_through_another_backend(self):
        """With the other account locked, its password doesn't log it in by its
        username, even though Alice's email still matches the same text."""
        self.lock_other()

        response = self.post(OTHER_PASSWORD)

        self.assertIsNone(self.logged_in_as())
        self.assertEqual(response.status_code, 200)
        self.post(PASSWORD)
        self.assertEqual(self.logged_in_as(), str(self.alice.pk))

    def test_one_account_reaching_the_limit_keeps_the_form_open(self):
        """Locking one match doesn't start the countdown while another can log in."""
        for _ in range(LOCKOUT_THRESHOLD - 1):
            self.client.post(self.url, {"username": "alice", "password": "wrong"})

        response = self.post("wrong")

        self.assertIsNone(response.context["lock_expiry"])
        self.assertEqual(response.context["remaining_attempts"], LOCKOUT_THRESHOLD - 1)
        self.post(OTHER_PASSWORD)
        self.assertEqual(self.logged_in_as(), str(self.other.pk))

    def test_countdown_ends_when_the_first_account_unlocks(self):
        """When every match is locked, the countdown uses the earliest expiry."""
        view = CustomLoginView()
        now = time.time()
        for user, seconds in ((self.alice, 100), (self.other, 500)):
            cache.set(
                view._get_lock_expiry_key(view._account_subject(user.pk)),
                now + seconds,
                600,
            )

        response = self.post("wrong")

        self.assertAlmostEqual(response.context["lock_expiry"], now + 100, delta=5)


class UnsupportedInputTests(TestCase):
    """Text the database can't store is rejected without a server error."""

    def setUp(self):
        cache.clear()
        self.url = reverse("login")

    def test_nul_character_in_identifier_is_an_ordinary_failure(self):
        """A NUL character gets the login page back, not an HTTP 500."""
        for _ in range(LOCKOUT_THRESHOLD):
            response = self.client.post(
                self.url, {"username": "ali\x00ce", "password": "wrong"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["lock_expiry"])
        locked = self.client.post(
            self.url, {"username": "ali\x00ce", "password": "wrong"}
        )
        self.assertEqual(locked.status_code, 200)


class SharedCacheTests(TestCase):
    """Lockouts live in a database cache shared by every server process."""

    def test_cache_uses_the_database_table(self):
        """The default cache is the database cache created by migration 0009."""
        default = settings.CACHES["default"]

        self.assertEqual(
            default["BACKEND"], "django.core.cache.backends.db.DatabaseCache"
        )
        self.assertIn(default["LOCATION"], connection.introspection.table_names())

    def test_values_round_trip_through_the_cache(self):
        """Values written to the cache can be read back."""
        cache.set("shared-cache-check", 3, 60)

        self.assertEqual(cache.get("shared-cache-check"), 3)
