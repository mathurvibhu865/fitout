from django.forms import ValidationError
from django.shortcuts import render

# Create your views here.
import json
import logging
from django.db.models import Q, Count, Sum, Min

import os
import traceback
from io import StringIO
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.db import connections, transaction, IntegrityError
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import viewsets, status, filters, exceptions, generics, permissions
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination
from fitout.db_router import set_current_tenant
from .utils import ensure_alias_for_client
from .serializers import PaymentModeSerializer


from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.db import transaction
from datetime import datetime
from django.utils import timezone
from django.db.models import Q
from rest_framework import generics, permissions, filters, exceptions
from django_filters.rest_framework import DjangoFilterBackend
from .models import FitoutType
from .serializers import FitoutTypeSerializer

from rest_framework.decorators import action


logger = logging.getLogger("fitout.api")
tax_logger = logging.getLogger("asset.taxonomy")
bundle_logger = logging.getLogger("asset.bundle")
from .models import (
    FitoutRequest, PaymentMode, WorkCategory, Status, DeviationStatus,
    Annexure,
    FitoutDeviation, FitoutDeviationImage, FitoutDeviationChat,
    FitoutRequestChat,
    FitoutChecklist, ChecklistQuestion, QuestionOption, ChecklistAnswer, FitoutGuide, WorkCategory

)



# -------------------------------------------------------------------
# Tenant helpers
# -------------------------------------------------------------------
def _get_tenant_from_request(request):
    tenant = getattr(request.user, "tenant", None)
    if not tenant:
        # Fallback: read from header
        alias = request.headers.get("X-Tenant-Alias")
        if alias:
            tenant = {"alias": alias}
    return tenant

def _ensure_alias_ready(tenant: dict) -> str:
    if not tenant or "alias" not in tenant:
        raise exceptions.AuthenticationFailed("Tenant alias missing in token.")
    alias = tenant["alias"]

    if alias not in settings.DATABASES:
        if tenant.get("client_username"):
            ensure_alias_for_client(client_username=tenant["client_username"])
        elif tenant.get("client_id"):
            ensure_alias_for_client(client_id=int(tenant["client_id"]))
        elif alias.startswith("client_"):
            ensure_alias_for_client(client_id=int(alias.split("_", 1)[1]))
        else:
            raise exceptions.APIException("Unable to resolve tenant DB.")
    return alias


class RouterTenantContextMixin(APIView):
    """Ensure DB router knows the tenant BEFORE any serializer/query runs."""
    def initial(self, request, *args, **kwargs):
        alias = _ensure_alias_ready(_get_tenant_from_request(request))
        set_current_tenant(alias)
        return super().initial(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        try:
            return super().finalize_response(request, response, *args, **kwargs)
        finally:
            set_current_tenant(None)


class TenantSerializerContextMixin:
    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        alias = _ensure_alias_ready(_get_tenant_from_request(self.request))
        ctx["alias"] = alias
        ctx["request"] = self.request
        return ctx


class _TenantDBMixin:
    def _alias(self) -> str:
        return _ensure_alias_ready(_get_tenant_from_request(self.request))





# -------------------------------------------------------------------
# Register/Prepare DB for a client
# -------------------------------------------------------------------
class RegisterDBByClientAPIView(APIView):
    authentication_classes = []
    permission_classes = []
    parser_classes = [JSONParser]

    def post(self, request):
        client_id = (request.data or {}).get("client_id")
        client_username = (request.data or {}).get("client_username")

        if not client_id and not client_username:
            return Response({"detail": "Provide client_id or client_username."}, status=400)

        try:
            alias = ensure_alias_for_client(
                client_id=int(client_id) if str(client_id).isdigit() else None,
                client_username=client_username if not client_id else None,
            )

            if settings.DEBUG or str(os.getenv("ASSET_AUTO_MIGRATE", "0")) == "1":
                out = StringIO()
                call_command("migrate", "api", database=alias, interactive=False, verbosity=1, stdout=out)
                logger.info("Migrated app 'api' on %s\n%s", alias, out.getvalue())

            try:
                connections[alias].close()
            except Exception:
                pass

            return Response({"detail": "Alias ready", "alias": alias}, status=201)

        except Exception as e:
            logger.exception("RegisterDBByClient failed")
            return Response({"detail": str(e)}, status=400)


from .serializers import (
    FitOutRequestSerializer,
    FitoutDeviationSerializer,
    FitoutChecklistSerializer,
    FitoutRequestChatSerializer,
    FitoutDeviationChatSerializer,
    ChecklistAnswerSerializer,
    AnnexureSerializer,
    WorkCategorySerializer,
    StatusSerializer,
    DeviationStatusSerializer,
    ChecklistQuestionSerializer,
    QuestionOptionSerializer,
    FitoutDeviationImageSerializer,
    WorkCategorySerializer,
    FitoutGuideSerializer,
)

from .pagination import StandardResultsSetPagination

class FitOutRequestViewSet(
    RouterTenantContextMixin,
    TenantSerializerContextMixin,
    _TenantDBMixin,
    viewsets.ModelViewSet
):
    serializer_class = FitOutRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [ 'tower_id', 'flat_id']
    search_fields = ['id', 'tower_id', 'flat_id', 'contractor_name']
    ordering_fields = ['id', 'created_at', 'requested_date']
    parser_classes = [MultiPartParser, FormParser]  # <-- allows file uploads

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return FitoutRequest.objects.using(alias).all()

    def perform_create(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                # Save main FitOutRequest
                instance = serializer.save()

                # Handle multi-file annexures
                annexure_ids = self.request.data.getlist("annexure_id")
                files = self.request.FILES.getlist("file")
                for annexure_id, file in zip(annexure_ids, files):
                    annexure_instance = Annexure.objects.using(alias).get(id=annexure_id)
                    Annexure.objects.using(alias).create(
                        fitout=instance,
                        annexure=annexure_instance,
                        file=file
                    )
                    # Automatically create a checklist
                    FitoutChecklist.objects.using(alias).create(
                        fitout_request=instance,
                        name=f"Checklist for {annexure_instance.name}",
                        category=annexure_instance.name,
                        sub_category=""
                    )
        except Exception as e:
            raise DRFValidationError(str(e))

    def perform_update(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                instance = serializer.save()

                # Replace existing annexures if new files are provided
                annexure_ids = self.request.data.getlist("annexure_id")
                files = self.request.FILES.getlist("file")
                if annexure_ids and files:
                    # Delete old annexures and checklists
                    instance.fitout_annexures.all().delete()
                    instance.checklists.filter(category__in=[Annexure.objects.using(alias).get(id=a).name for a in annexure_ids]).delete()

                    # Create new annexures and checklists
                    for annexure_id, file in zip(annexure_ids, files):
                        annexure_instance = Annexure.objects.using(alias).get(id=annexure_id)
                        Annexure.objects.using(alias).create(
                            fitout=instance,
                            annexure=annexure_instance,
                            file=file
                        )
                        FitoutChecklist.objects.using(alias).create(
                            fitout_request=instance,
                            name=f"Checklist for {annexure_instance.name}",
                            category=annexure_instance.name,
                            sub_category=""
                        )
        except Exception as e:
            raise DRFValidationError(str(e))

    def perform_destroy(self, instance):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                instance.delete(using=alias)
        except IntegrityError as e:
            raise DRFValidationError(str(e))
        
        
        
        
class FitoutTypeViewSet(
    RouterTenantContextMixin,
    TenantSerializerContextMixin,
    _TenantDBMixin,
    viewsets.ModelViewSet
):
    serializer_class = FitoutTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['flat_type', 'status']
    search_fields = ['id', 'name', 'code', 'flat_type']
    ordering_fields = ['id', 'created_at', 'updated_at']
    parser_classes = [MultiPartParser, FormParser]  # allows file uploads if needed

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return FitoutType.objects.using(alias).all()

    def perform_create(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                instance = serializer.save(using=alias)

                # Optional: handle dynamic move-in status options if provided
                movein_options = self.request.data.get("movein_status_options")
                if movein_options:
                    instance.movein_status_options = movein_options
                    instance.save(using=alias)
        except Exception as e:
            raise DRFValidationError(str(e))

    def perform_update(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                instance = serializer.save(using=alias)

                # Optional: update move-in status options
                movein_options = self.request.data.get("movein_status_options")
                if movein_options:
                    instance.movein_status_options = movein_options
                    instance.save(using=alias)
        except Exception as e:
            raise DRFValidationError(str(e))

    def perform_destroy(self, instance):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                instance.delete(using=alias)
        except IntegrityError as e:
            raise DRFValidationError(str(e))
                
class PaymentModeViewSet(
    RouterTenantContextMixin,
    TenantSerializerContextMixin,
    _TenantDBMixin,
    viewsets.ModelViewSet
):
    queryset = PaymentMode.objects.all()
    serializer_class = PaymentModeSerializer

    def perform_create(self, serializer):
        name = self.request.data.get("name")
        if not name:
            raise ValidationError({"name": "This field is required."})

        if PaymentMode.objects.filter(name=name).exists():
            raise ValidationError({"name": f"PaymentMode with name '{name}' already exists."})

        serializer.save()        

class FitoutDeviationViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    """
    API endpoint for managing fit-out deviations.
    """
    serializer_class = FitoutDeviationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'fitout_request']
    search_fields = ['description', 'fitout_request__id']
    ordering_fields = ['id', 'created_at']

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return FitoutDeviation.objects.using(alias).all()

    def perform_create(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                serializer.save()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
        except IntegrityError as e:
            raise DRFValidationError(str(e))
    
    def perform_update(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                serializer.save()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
        except IntegrityError as e:
            raise DRFValidationError(str(e))

    def perform_destroy(self, instance):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                instance.delete(using=alias)
        except IntegrityError as e:
            raise DRFValidationError(str(e))


class FitoutChecklistViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    """
    API endpoint for managing fit-out checklists.
    """
    serializer_class = FitoutChecklistSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['fitout_request', 'work_category', 'sub_category']
    search_fields = ['name']
    ordering_fields = ['id', 'created_at', 'status']

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return FitoutChecklist.objects.using(alias).all()

    def perform_create(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                serializer.save()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
        except IntegrityError as e:
            raise DRFValidationError(str(e))

    def perform_update(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                serializer.save()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
        except IntegrityError as e:
            raise DRFValidationError(str(e))

    def perform_destroy(self, instance):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                instance.delete(using=alias)
        except IntegrityError as e:
            raise DRFValidationError(str(e))


# class FitoutRequestChatViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
#     queryset = FitoutRequestChat.objects.all()
#     serializer_class = FitoutRequestChatSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         alias = self._alias()
#         if not alias:
#             raise DRFValidationError("Tenant DB alias missing.")
#         return FitoutRequestChat.objects.using(alias).all()



class FitoutRequestChatViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin,viewsets.ModelViewSet):
    queryset = FitoutRequestChat.objects.all()
    serializer_class = FitoutRequestChatSerializer

    def perform_create(self, serializer):
        fitout_request_id = self.request.data.get("fitout_request")

        if not fitout_request_id:
            raise ValidationError({"fitout_request": "This field is required."})

        try:
            fitout_request = FitoutRequest.objects.get(id=fitout_request_id)
        except FitoutRequest.DoesNotExist:
            raise ValidationError({"fitout_request": f"FitOutRequest with id {fitout_request_id} does not exist."})

        serializer.save(fitout_request=fitout_request)
        
        
class FitoutDeviationChatViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    queryset = FitoutDeviationChat.objects.all()
    serializer_class = FitoutDeviationChatSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return FitoutDeviationChat.objects.using(alias).all()


class ChecklistAnswerViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    queryset = ChecklistAnswer.objects.all()
    serializer_class = ChecklistAnswerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return ChecklistAnswer.objects.using(alias).all()


class AnnexureViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    queryset = Annexure.objects.all()
    serializer_class = AnnexureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return Annexure.objects.using(alias).all()


# class WorkCategoryViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
#     queryset = WorkCategory.objects.all()
#     serializer_class = WorkCategorySerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         alias = self._alias()
#         if not alias:
#             raise DRFValidationError("Tenant DB alias missing.")
#         return WorkCategory.objects.using(alias).all()


class StatusViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
  
    serializer_class = StatusSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return Status.objects.using(alias).all()


class DeviationStatusViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    queryset = DeviationStatus.objects.all()
    serializer_class = DeviationStatusSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return DeviationStatus.objects.using(alias).all()


# class AssociationViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
#     queryset = Association.objects.all()
#     serializer_class = AssociationSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         alias = self._alias()
#         if not alias:
#             raise DRFValidationError("Tenant DB alias missing.")
#         return Association.objects.using(alias).all()
    
    
class ChecklistQuestionViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    queryset = ChecklistQuestion.objects.all()
    serializer_class = ChecklistQuestionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        alias = self._alias()
        return ChecklistQuestion.objects.using(alias).all()


class QuestionOptionViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    queryset = QuestionOption.objects.all()
    serializer_class = QuestionOptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        alias = self._alias()
        return QuestionOption.objects.using(alias).all()
    
    
class FitoutDeviationImageViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    queryset = FitoutDeviationImage.objects.all()
    serializer_class = FitoutDeviationImageSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]  # needed for file uploads

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return FitoutDeviationImage.objects.using(alias).all()
    

class WorkCategoryViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    serializer_class = WorkCategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return WorkCategory.objects.using(alias).all()

    def perform_create(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                serializer.save()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
        except IntegrityError as e:
            raise DRFValidationError(str(e))

    def perform_update(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                serializer.save()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
        except IntegrityError as e:
            raise DRFValidationError(str(e))

    def perform_destroy(self, instance):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                instance.delete(using=alias)
        except IntegrityError as e:
            raise DRFValidationError(str(e))
        
class SubCategoryViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    serializer_class = WorkCategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return SubCategory.objects.using(alias).all()

    def perform_create(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                serializer.save()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
        except IntegrityError as e:
            raise DRFValidationError(str(e))

    def perform_update(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                serializer.save()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
        except IntegrityError as e:
            raise DRFValidationError(str(e))

    def perform_destroy(self, instance):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                instance.delete(using=alias)
        except IntegrityError as e:
            raise DRFValidationError(str(e))
        


class FitoutGuideViewSet(RouterTenantContextMixin, TenantSerializerContextMixin, _TenantDBMixin, viewsets.ModelViewSet):
    serializer_class = FitoutGuideSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        alias = self._alias()
        if not alias:
            raise DRFValidationError("Tenant DB alias missing.")
        return FitoutGuide.objects.using(alias).all()

    def perform_create(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                serializer.save()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
        except IntegrityError as e:
            raise DRFValidationError(str(e))

    def perform_update(self, serializer):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                serializer.save()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
        except IntegrityError as e:
            raise DRFValidationError(str(e))

    def perform_destroy(self, instance):
        alias = self._alias()
        try:
            with transaction.atomic(using=alias):
                instance.delete(using=alias)
        except IntegrityError as e:
            raise DRFValidationError(str(e))
        
        
        
class WorkCategoryCreateAPIView(APIView):
     def post(self, request, *args, **kwargs):
        serializer = WorkCategorySerializer(data=request.data)
        if serializer.is_valid():
            category = serializer.save()
            return Response({
                "id": category.id,
                "name": category.name,
                "description": category.description,
                "fitout_request": category.fitout_request.id
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)