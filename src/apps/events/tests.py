from __future__ import annotations

import uuid
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserProfile
from apps.communities.models import Community, CommunityMember
from apps.events.models import Event, EventSpeaker, EventSponsor, EventGalleryImage, EventRSVP, EventReminder, EventComment

User = get_user_model()


class EventAPITests(APITestCase):
    def setUp(self):
        from unittest.mock import patch
        # Mock SupabaseStorage to isolate tests from actual storage calls
        self.storage_save_patcher = patch('apps.accounts.storage.SupabaseStorage._save')
        self.mock_storage_save = self.storage_save_patcher.start()
        self.mock_storage_save.side_effect = lambda name, content: name

        self.storage_url_patcher = patch('apps.accounts.storage.SupabaseStorage.url')
        self.mock_storage_url = self.storage_url_patcher.start()
        self.mock_storage_url.side_effect = lambda name: f"/media/{name}"

        self.storage_exists_patcher = patch('apps.accounts.storage.SupabaseStorage.exists')
        self.mock_storage_exists = self.storage_exists_patcher.start()
        self.mock_storage_exists.return_value = False

        # Create test users
        self.admin_user = User.objects.create_user(username="admin_user", email="admin@example.com", password="Password123")
        self.student_user = User.objects.create_user(username="student_user", email="student@example.com", password="Password123")
        self.student_user2 = User.objects.create_user(username="student_user2", email="student2@example.com", password="Password123")

        # Set roles
        self.admin_profile = self.admin_user.profile
        self.admin_profile.role = UserProfile.Role.ADMIN
        self.admin_profile.college = "Engineering College"
        self.admin_profile.save()

        self.student_profile = self.student_user.profile
        self.student_profile.role = UserProfile.Role.STUDENT
        self.student_profile.college = "Engineering College"
        self.student_profile.save()

        self.student_profile2 = self.student_user2.profile
        self.student_profile2.role = UserProfile.Role.STUDENT
        self.student_profile2.college = "Engineering College"
        self.student_profile2.save()

        # Set up a community
        self.community = Community.objects.create(
            name="Event Creators",
            description="Event community",
            is_public=True
        )
        CommunityMember.objects.create(community=self.community, user=self.student_user, role=CommunityMember.Role.MEMBER)

    def tearDown(self):
        self.storage_save_patcher.stop()
        self.storage_url_patcher.stop()
        self.storage_exists_patcher.stop()

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    # --- CRUD & Scopes ---

    def test_create_event_permissions(self):
        # 1. Student cannot create platform event
        self.authenticate(self.student_user)
        url = reverse("events-list")
        data = {
            "title": "Hackathon 2026",
            "description": "Fun times",
            "scope": "platform",
            "event_type": "offline",
            "location": "Auditorium",
            "start_time": (timezone.now() + timedelta(days=1)).isoformat(),
            "end_time": (timezone.now() + timedelta(days=1, hours=2)).isoformat(),
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Admin can create platform event
        self.authenticate(self.admin_user)
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["success"], True)
        self.assertEqual(response.data["data"]["title"], "Hackathon 2026")

    def test_scope_validation(self):
        self.authenticate(self.admin_user)
        url = reverse("events-list")
        
        # Missing community for community scope
        data = {
            "title": "Community Hackathon",
            "description": "Fun times",
            "scope": "community",
            "event_type": "online",
            "start_time": (timezone.now() + timedelta(days=1)).isoformat(),
            "end_time": (timezone.now() + timedelta(days=1, hours=2)).isoformat(),
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("community", response.data["errors"])

    # --- RSVP and Waitlist Queue & Auto-Promotion ---

    def test_rsvp_capacity_waitlist_and_promotion(self):
        # Create event with 1 seat capacity
        event = Event.objects.create(
            title="Sized Event",
            description="Only 1 person",
            scope="platform",
            event_type="online",
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
            seats=1,
            author=self.admin_user
        )

        join_url = reverse("events-join", kwargs={"pk": event.id})
        leave_url = reverse("events-leave", kwargs={"pk": event.id})

        # 1. First user joins (gets status 'joined')
        self.authenticate(self.student_user)
        response = self.client.post(join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["status"], "joined")
        self.assertTrue(EventRSVP.objects.filter(event=event, user=self.student_user, status=EventRSVP.Status.JOINED).exists())

        # 2. Second user joins (gets status 'waiting_list')
        self.authenticate(self.student_user2)
        response = self.client.post(join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["status"], "waiting_list")
        self.assertTrue(EventRSVP.objects.filter(event=event, user=self.student_user2, status=EventRSVP.Status.WAITING_LIST).exists())

        # 3. First user leaves (confirms promotion)
        self.authenticate(self.student_user)
        response = self.client.post(leave_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(EventRSVP.objects.filter(event=event, user=self.student_user).exists())

        # Second user should be automatically promoted to 'joined'
        rsvp2 = EventRSVP.objects.get(event=event, user=self.student_user2)
        self.assertEqual(rsvp2.status, EventRSVP.Status.JOINED)

    # --- Attendance Check-in via QR ---

    def test_attendance_check_in(self):
        event = Event.objects.create(
            title="Attendable Event",
            description="Checking-in",
            scope="platform",
            event_type="offline",
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
            seats=10,
            author=self.admin_user
        )

        # Student user joins
        self.authenticate(self.student_user)
        self.client.post(reverse("events-join", kwargs={"pk": event.id}))

        check_in_url = reverse("events-check-in", kwargs={"pk": event.id})

        # 1. Invalid QR Key
        response = self.client.post(check_in_url, {"qr_code_key": str(uuid.uuid4())})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # 2. Valid QR Key
        response = self.client.post(check_in_url, {"qr_code_key": str(event.qr_code_key)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["attended"], True)
        
        rsvp = EventRSVP.objects.get(event=event, user=self.student_user)
        self.assertTrue(rsvp.attended)

    # --- Calendar Export (.ics) ---

    def test_calendar_export(self):
        event = Event.objects.create(
            title="Cal Event",
            description="Export me",
            scope="platform",
            event_type="online",
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
            author=self.admin_user
        )

        self.authenticate(self.student_user)
        url = reverse("events-ical", kwargs={"pk": event.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/calendar")
        self.assertIn("BEGIN:VCALENDAR", response.content.decode())
        self.assertIn("SUMMARY:Cal Event", response.content.decode())

    # --- Reminders ---

    def test_reminders(self):
        event = Event.objects.create(
            title="Reminder Event",
            description="Ping me",
            scope="platform",
            event_type="online",
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
            author=self.admin_user
        )

        self.authenticate(self.student_user)
        url = reverse("events-remind", kwargs={"pk": event.id})

        # Reminder in past (invalid)
        response = self.client.post(url, {"reminder_time": (timezone.now() - timedelta(minutes=10)).isoformat()})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Reminder in future (valid)
        future_reminder = (timezone.now() + timedelta(hours=10)).isoformat()
        response = self.client.post(url, {"reminder_time": future_reminder})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(EventReminder.objects.filter(event=event, user=self.student_user).exists())

    # --- Comments ---

    def test_comments(self):
        event = Event.objects.create(
            title="Discussion Event",
            description="Discuss.",
            scope="platform",
            event_type="online",
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
            author=self.admin_user
        )

        self.authenticate(self.student_user)
        url = reverse("events-comments", kwargs={"pk": event.id})

        # Add comment
        response = self.client.post(url, {"content": "I am coming!"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["content"], "I am coming!")
        self.assertTrue(EventComment.objects.filter(event=event, user=self.student_user, content="I am coming!").exists())

    # --- Speaker/Sponsor/Gallery uploads ---

    def test_gallery_speaker_sponsor(self):
        event = Event.objects.create(
            title="Big Event",
            description="Speakers and sponsors",
            scope="platform",
            event_type="hybrid",
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
            author=self.admin_user
        )

        self.authenticate(self.admin_user)

        # Add speaker
        speaker_url = reverse("events-add-speaker", kwargs={"pk": event.id})
        response = self.client.post(speaker_url, {"name": "Speaker Bob", "bio": "Expert in AI"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EventSpeaker.objects.filter(event=event, name="Speaker Bob").exists())

        # Add sponsor
        sponsor_url = reverse("events-add-sponsor", kwargs={"pk": event.id})
        response = self.client.post(sponsor_url, {"name": "Google Tech"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EventSponsor.objects.filter(event=event, name="Google Tech").exists())

        # Upload gallery image
        gallery_url = reverse("events-gallery", kwargs={"pk": event.id})
        img = SimpleUploadedFile("banner.png", b"image content", content_type="image/png")
        response = self.client.post(gallery_url, {"images": [img]}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EventGalleryImage.objects.filter(event=event).exists())
