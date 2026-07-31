from __future__ import annotations

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from apps.common.responses import error_response, success_response

from .models import UserProfile, UserStorageUsage
from .storage import SupabaseStorage
from .serializers import (
    CurrentUserSerializer,
    FirebaseLoginSerializer,
    JWTRefreshSerializer,
    LogoutSerializer,
    ProfileUpdateSerializer,
    UserProfileSerializer,
)
from .services import get_or_create_user_profile


class FirebaseLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = FirebaseLoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return success_response(
            message="Firebase login successful",
            data={
                "access": serializer.validated_data["access"],
                "refresh": serializer.validated_data["refresh"],
                "user": UserProfileSerializer(get_or_create_user_profile(serializer.validated_data["user"])).data,
            },
        )


class JWTRefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = JWTRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token_serializer = TokenRefreshSerializer(data=serializer.validated_data)
            token_serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            return error_response(
                message="Invalid or expired refresh token.",
                errors={"refresh": str(exc)},
                status_code=400,
            )
        return success_response(
            message="JWT refreshed successfully",
            data={"access": token_serializer.validated_data["access"]},
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(message="Logout successful", data={"logged_out": True})


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return success_response(
            message="Current user retrieved successfully",
            data=CurrentUserSerializer.from_user(request.user),
        )


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        profile = get_or_create_user_profile(request.user)
        return success_response(
            message="Profile retrieved successfully",
            data=UserProfileSerializer(profile).data,
        )

    def patch(self, request, *args, **kwargs):
        profile = get_or_create_user_profile(request.user)
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_profile = serializer.save()
        return success_response(
            message="Profile updated successfully",
            data=UserProfileSerializer(updated_profile).data,
        )


from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from .permissions import IsProfileOwnerOrReadOnly


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return success_response(
            message="Profiles retrieved successfully",
            data={
                "results": data,
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
            }
        )


class UserProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated, IsProfileOwnerOrReadOnly]
    pagination_class = StandardResultsSetPagination
    lookup_field = "username"

    def get_queryset(self):
        queryset = UserProfile.objects.select_related("user").all()

        # College Filter
        college = self.request.query_params.get("college")
        if college:
            queryset = queryset.filter(college__iexact=college)

        # Branch Filter
        branch = self.request.query_params.get("branch")
        if branch:
            queryset = queryset.filter(branch__iexact=branch)

        # Year Filter
        year = self.request.query_params.get("year")
        if year:
            try:
                queryset = queryset.filter(year=int(year))
            except ValueError:
                pass

        # Skill Filter (comma separated)
        skills_param = self.request.query_params.get("skills")
        if skills_param:
            skills = [s.strip() for s in skills_param.split(",") if s.strip()]
            for skill in skills:
                queryset = queryset.filter(skills__icontains=skill)

        # Interest Filter (comma separated)
        interests_param = self.request.query_params.get("interests")
        if interests_param:
            interests = [i.strip() for i in interests_param.split(",") if i.strip()]
            for interest in interests:
                queryset = queryset.filter(interests__icontains=interest)

        # General Search (username, full_name, bio, location, skills, interests)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(full_name__icontains=search) |
                Q(bio__icontains=search) |
                Q(location__icontains=search) |
                Q(skills__icontains=search) |
                Q(interests__icontains=search)
            )

        return queryset.order_by("username")

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_val = self.kwargs[lookup_url_kwarg]
        
        filter_kwargs = {f"{self.lookup_field}__iexact": lookup_val}
        obj = get_object_or_404(queryset, **filter_kwargs)
        
        self.check_object_permissions(self.request, obj)
        return obj

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return success_response(message="Profiles retrieved successfully", data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(message="Profile retrieved successfully", data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if UserProfile.objects.filter(user=user).exists():
            return error_response(message="Profile already exists for this user", status_code=400)
            
        self.perform_create(serializer)
        return success_response(message="Profile created successfully", data=serializer.data, status_code=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return success_response(message="Profile updated successfully", data=serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response(message="Profile deleted successfully", data={"deleted": True})


class StorageViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @action(detail=False, methods=["post"])
    def upload(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            return error_response(message="No file provided.", status_code=400)

        storage = SupabaseStorage()
        try:
            saved_name = storage._save(file_obj.name, file_obj)
            public_url = storage.url(saved_name)
            try:
                final_size = file_obj.size
            except Exception:
                final_size = 0

            return success_response(
                message="File uploaded successfully.",
                data={
                    "file_name": saved_name,
                    "url": public_url,
                    "size_bytes": final_size
                }
            )
        except Exception as e:
            return error_response(message=str(e), status_code=400)

    @action(detail=False, methods=["post"], url_path="signed-url")
    def signed_url(self, request):
        file_name = request.data.get("file_name")
        if not file_name:
            return error_response(message="file_name is required.", status_code=400)

        expires_in = int(request.data.get("expires_in", 3600))
        storage = SupabaseStorage()
        signed_url = storage.get_signed_url(file_name, expires_in=expires_in)
        return success_response(
            message="Signed URL generated successfully.",
            data={
                "signed_url": signed_url
            }
        )

    @action(detail=False, methods=["get"])
    def quota(self, request):
        usage, _ = UserStorageUsage.objects.get_or_create(user=request.user)
        return success_response(
            message="User storage quota retrieved.",
            data={
                "bytes_used": usage.bytes_used,
                "limit_bytes": 100 * 1024 * 1024
            }
        )

