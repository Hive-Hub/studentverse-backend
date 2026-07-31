from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserProfile
from apps.accounts.permissions import IsAdmin, IsModerator, IsModeratorOrAdmin, IsStudent


class FirebaseLoginTests(APITestCase):
    def setUp(self):
        self.firebase_payload = {
            "uid": "firebase-uid-123",
            "email": "student@example.com",
            "name": "Student Verse",
            "role": "moderator",
        }

    @patch("apps.accounts.serializers.firebase_auth.verify_id_token")
    @patch("apps.accounts.serializers.get_firebase_app")
    def test_firebase_login_creates_user_and_returns_jwt(self, mock_get_app, mock_verify):
        mock_get_app.return_value = object()
        mock_verify.return_value = self.firebase_payload

        response = self.client.post(
            reverse("firebase-login"),
            data={"firebase_id_token": "valid-firebase-token-value"},
            format="json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["data"])
        self.assertIn("refresh", response.data["data"])

        user = get_user_model().objects.get(username="firebase-uid-123")
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.firebase_uid, "firebase-uid-123")
        self.assertEqual(profile.role, UserProfile.Role.MODERATOR)

    @patch("apps.accounts.serializers.firebase_auth.verify_id_token")
    @patch("apps.accounts.serializers.get_firebase_app")
    def test_firebase_login_accepts_authorization_header(self, mock_get_app, mock_verify):
        mock_get_app.return_value = object()
        mock_verify.return_value = self.firebase_payload

        response = self.client.post(
            reverse("firebase-login"),
            data={},
            format="json",
            HTTP_ACCEPT="application/json",
            HTTP_AUTHORIZATION="Bearer valid-firebase-token-value",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class JWTFlowTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="firebase-uid-999", email="user@example.com")
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.firebase_uid = "firebase-uid-999"
        self.profile.role = UserProfile.Role.ADMIN
        self.profile.display_name = "Admin User"
        self.profile.save(update_fields=["firebase_uid", "role", "display_name"])
        self.refresh = RefreshToken.for_user(self.user)
        self.access = str(self.refresh.access_token)

    def test_current_user_endpoint_returns_user_summary(self):
        response = self.client.get(
            reverse("current-user"),
            HTTP_ACCEPT="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["role"], "admin")
        self.assertEqual(response.data["data"]["username"], "firebase-uid-999")

    def test_profile_endpoint_returns_profile(self):
        response = self.client.get(
            reverse("profile"),
            HTTP_ACCEPT="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["firebase_uid"], "firebase-uid-999")
        self.assertEqual(response.data["data"]["role"], "admin")

    def test_profile_patch_updates_display_name(self):
        response = self.client.patch(
            reverse("profile"),
            data={"display_name": "Updated Admin"},
            format="json",
            HTTP_ACCEPT="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.display_name, "Updated Admin")

    def test_refresh_endpoint_returns_new_access_token(self):
        response = self.client.post(
            reverse("jwt-refresh"),
            data={"refresh": str(self.refresh)},
            format="json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["data"])

    def test_logout_blacklists_refresh_token(self):
        response = self.client.post(
            reverse("logout"),
            data={"refresh": str(self.refresh)},
            format="json",
            HTTP_ACCEPT="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        refresh_again = self.client.post(
            reverse("jwt-refresh"),
            data={"refresh": str(self.refresh)},
            format="json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(refresh_again.status_code, status.HTTP_400_BAD_REQUEST)


class PermissionTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.student = User.objects.create_user(username="student-user")
        self.moderator = User.objects.create_user(username="moderator-user")
        self.admin = User.objects.create_user(username="admin-user")
        self.student_profile = UserProfile.objects.get(user=self.student)
        self.moderator_profile = UserProfile.objects.get(user=self.moderator)
        self.admin_profile = UserProfile.objects.get(user=self.admin)
        self.moderator_profile.role = UserProfile.Role.MODERATOR
        self.moderator_profile.save(update_fields=["role"])
        self.admin_profile.role = UserProfile.Role.ADMIN
        self.admin_profile.save(update_fields=["role"])

    def test_role_permissions(self):
        class DummyRequest:
            def __init__(self, user):
                self.user = user

        self.assertTrue(IsStudent().has_permission(DummyRequest(self.student), None))
        self.assertTrue(IsModerator().has_permission(DummyRequest(self.moderator), None))
        self.assertTrue(IsAdmin().has_permission(DummyRequest(self.admin), None))
        self.assertTrue(IsModeratorOrAdmin().has_permission(DummyRequest(self.admin), None))


from django.core.files.uploadedfile import SimpleUploadedFile


class UserProfileCRUDTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user1 = User.objects.create_user(username="user1", email="user1@example.com")
        self.profile1 = UserProfile.objects.get(user=self.user1)
        self.profile1.username = "alpha_handle"
        self.profile1.full_name = "Alpha Fullname"
        self.profile1.college = "Engineering College"
        self.profile1.branch = "Computer Science"
        self.profile1.year = 3
        self.profile1.skills = ["Python", "Django"]
        self.profile1.interests = ["Cybersecurity", "Gaming"]
        self.profile1.save()

        self.user2 = User.objects.create_user(username="user2", email="user2@example.com")
        self.profile2 = UserProfile.objects.get(user=self.user2)
        self.profile2.username = "beta_handle"
        self.profile2.full_name = "Beta Fullname"
        self.profile2.college = "Science College"
        self.profile2.branch = "Mathematics"
        self.profile2.year = 2
        self.profile2.skills = ["Python", "R"]
        self.profile2.interests = ["AI", "Reading"]
        self.profile2.save()

        self.refresh = RefreshToken.for_user(self.user1)
        self.access = str(self.refresh.access_token)

    def test_list_profiles_authenticated(self):
        response = self.client.get(
            "/api/v1/profiles/",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["success"], True)
        self.assertIn("results", response.data["data"])
        self.assertEqual(len(response.data["data"]["results"]), 2)

    def test_list_profiles_unauthenticated(self):
        response = self.client.get("/api/v1/profiles/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_profile_by_username_case_insensitive(self):
        response = self.client.get(
            "/api/v1/profiles/ALPHA_HANDLE/",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["username"], "alpha_handle")
        self.assertEqual(response.data["data"]["full_name"], "Alpha Fullname")

    def test_filter_profiles(self):
        # Filter by college
        response = self.client.get(
            "/api/v1/profiles/?college=Engineering College",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)
        self.assertEqual(response.data["data"]["results"][0]["username"], "alpha_handle")

        # Filter by year
        response = self.client.get(
            "/api/v1/profiles/?year=2",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)
        self.assertEqual(response.data["data"]["results"][0]["username"], "beta_handle")

    def test_search_profiles(self):
        # Search by interest
        response = self.client.get(
            "/api/v1/profiles/?search=AI",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)
        self.assertEqual(response.data["data"]["results"][0]["username"], "beta_handle")


        # Search by full_name
        response = self.client.get(
            "/api/v1/profiles/?search=Alpha",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)
        self.assertEqual(response.data["data"]["results"][0]["username"], "alpha_handle")

    def test_update_own_profile_success(self):
        payload = {
            "username": "new_alpha_handle",
            "full_name": "Updated Alpha",
            "bio": "New Bio",
            "year": 4,
            "skills": ["Python", "Rust"],
            "github": "https://github.com/alpha",
            "linkedin": "https://linkedin.com/in/alpha"
        }
        response = self.client.patch(
            f"/api/v1/profiles/{self.profile1.username}/",
            data=payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile1.refresh_from_db()
        self.assertEqual(self.profile1.username, "new_alpha_handle")
        self.assertEqual(self.profile1.full_name, "Updated Alpha")
        self.assertEqual(self.profile1.bio, "New Bio")
        self.assertEqual(self.profile1.year, 4)
        self.assertEqual(self.profile1.skills, ["Python", "Rust"])
        self.assertEqual(self.profile1.github, "https://github.com/alpha")

    def test_update_own_profile_validation_errors(self):
        # Invalid username handle (special character)
        payload = {"username": "alpha-handle!"}
        response = self.client.patch(
            f"/api/v1/profiles/{self.profile1.username}/",
            data=payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Invalid year (out of bounds)
        payload = {"year": 6}
        response = self.client.patch(
            f"/api/v1/profiles/{self.profile1.username}/",
            data=payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Invalid social URL domains
        payload = {"github": "https://gitlab.com/alpha"}
        response = self.client.patch(
            f"/api/v1/profiles/{self.profile1.username}/",
            data=payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_other_profile_forbidden(self):
        payload = {"bio": "Malicious edit"}
        response = self.client.patch(
            f"/api/v1/profiles/{self.profile2.username}/",
            data=payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_other_profile_forbidden(self):
        response = self.client.delete(
            f"/api/v1/profiles/{self.profile2.username}/",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_own_profile_success(self):
        response = self.client.delete(
            f"/api/v1/profiles/{self.profile1.username}/",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(UserProfile.objects.filter(pk=self.profile1.pk).exists())

    def test_upload_profile_photo_validation(self):
        # Test large file upload (> 5MB)
        large_file = SimpleUploadedFile("avatar.png", b"0" * (6 * 1024 * 1024), content_type="image/png")
        response = self.client.patch(
            f"/api/v1/profiles/{self.profile1.username}/",
            data={"profile_photo": large_file},
            format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("profile_photo", response.data["errors"])

        # Test invalid extension
        bad_file = SimpleUploadedFile("avatar.txt", b"some text content", content_type="text/plain")
        response = self.client.patch(
            f"/api/v1/profiles/{self.profile1.username}/",
            data={"profile_photo": bad_file},
            format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.storage import SupabaseStorage
from apps.accounts.models import UserStorageUsage


class SupabaseStorageTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="storage_user", email="storage@example.com")
        self.storage = SupabaseStorage()
        
        self.post_patcher = patch("requests.post")
        self.mock_post = self.post_patcher.start()
        self.mock_post.return_value.status_code = 201
        self.mock_post.return_value.json.return_value = {"signedURL": "/temp-signed-path"}
        
        self.put_patcher = patch("requests.put")
        self.mock_put = self.put_patcher.start()
        self.mock_put.return_value.status_code = 200

        self.delete_patcher = patch("requests.delete")
        self.mock_delete = self.delete_patcher.start()
        self.mock_delete.return_value.status_code = 200

    def tearDown(self):
        self.post_patcher.stop()
        self.put_patcher.stop()
        self.delete_patcher.stop()

    def test_file_type_and_size_validation(self):
        # 1. Unsupported format .exe
        bad_file = SimpleUploadedFile("danger.exe", b"binary", content_type="application/octet-stream")
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.storage._save("danger.exe", bad_file)

        # 2. Image size exceeding 5MB limit
        large_image_data = b"x" * (6 * 1024 * 1024)
        large_img = SimpleUploadedFile("large.png", large_image_data, content_type="image/png")
        with self.assertRaises(ValidationError):
            self.storage._save("large.png", large_img)

    def test_image_compression(self):
        from PIL import Image
        from io import BytesIO
        img = Image.new("RGBA", (100, 100), color="red")
        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)
        img_data = img_io.read()
        
        img_file = SimpleUploadedFile("test_img.png", img_data, content_type="image/png")
        saved_name = self.storage._save("test_img.png", img_file)
        self.assertEqual(saved_name, "test_img.png")

    def test_storage_quota(self):
        usage, _ = UserStorageUsage.objects.get_or_create(user=self.user)
        usage.bytes_used = 99 * 1024 * 1024
        usage.save()

        from apps.accounts.middleware import CurrentUserMiddleware
        CurrentUserMiddleware.set_current_user(self.user)
        try:
            # Uploading a 2MB file exceeds 100MB limit
            large_doc = SimpleUploadedFile("doc.pdf", b"x" * (2 * 1024 * 1024), content_type="application/pdf")
            from django.core.exceptions import ValidationError
            with self.assertRaises(ValidationError):
                self.storage._save("doc.pdf", large_doc)
        finally:
            CurrentUserMiddleware.clear_current_user()

    def test_signed_url_generation(self):
        url = self.storage.get_signed_url("avatar.png", expires_in=3600)
        self.assertIsNotNone(url)


class StorageViewSetAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="storage_api_user", email="storage_api@example.com")
        self.refresh = RefreshToken.for_user(self.user)
        self.access = str(self.refresh.access_token)

        self.post_patcher = patch("requests.post")
        self.mock_post = self.post_patcher.start()
        self.mock_post.return_value.status_code = 201
        self.mock_post.return_value.json.return_value = {"signedURL": "/temp-signed-path"}

    def tearDown(self):
        self.post_patcher.stop()

    def test_upload_file_api(self):
        url = reverse("storage-upload")
        txt_file = SimpleUploadedFile("test.txt", b"my text content", content_type="text/plain")
        response = self.client.post(
            url,
            data={"file": txt_file},
            format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {self.access}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("url", response.data["data"])
        self.assertIn("file_name", response.data["data"])

    def test_upload_invalid_file_type_api(self):
        url = reverse("storage-upload")
        bad_file = SimpleUploadedFile("danger.exe", b"executable bytes", content_type="application/octet-stream")
        response = self.client.post(
            url,
            data={"file": bad_file},
            format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {self.access}"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quota_retrieval_api(self):
        url = reverse("storage-quota")
        response = self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {self.access}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("bytes_used", response.data["data"])
        self.assertEqual(response.data["data"]["limit_bytes"], 100 * 1024 * 1024)

    def test_signed_url_api(self):
        url = reverse("storage-signed-url")
        response = self.client.post(
            url,
            data={"file_name": "avatar.png"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("signed_url", response.data["data"])


