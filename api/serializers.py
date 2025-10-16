from rest_framework import serializers
from .models import FitoutType
from rest_framework.validators import UniqueTogetherValidator, UniqueValidator
from .models import (
    Annexure,
    PaymentMode,
    SubCategory,
    WorkCategory,
    FitoutRequest,
    # FitOutAnnexure,
    Status,
    DeviationStatus,
    FitoutDeviation,
    FitoutDeviationImage,
    FitoutDeviationChat,
    FitoutRequestChat,
    FitoutChecklist,
    ChecklistQuestion,
    QuestionOption,
    ChecklistAnswer,
    # CategoryAnnexure,
    FitoutGuide
)


# ---------------- Alias Serializer Base ----------------
class AliasContextMin:
    """Ensures the database alias is present in the serializer context."""
    @property
    def alias(self) -> str:
        alias = self.context.get('alias')
        if not alias:
            raise RuntimeError("Serializer context missing 'alias'.")
        return alias


class AliasModelSerializer(AliasContextMin, serializers.ModelSerializer):
    """
    Custom ModelSerializer that routes unique validators
    to the correct database alias.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for v in self.validators:
            if isinstance(v, (UniqueTogetherValidator, UniqueValidator)) and getattr(v, 'queryset', None) is not None:
                v.queryset = v.queryset.using(self.alias)
        
        for field in self.fields.values():
            for val in getattr(field, "validators", []):
                if isinstance(val, UniqueValidator) and getattr(val, "queryset", None) is not None:
                    val.queryset = val.queryset.using(self.alias)


# ---------------- Core Fitout Serializers ----------------
# class AnnexureImageSerializer(AliasModelSerializer):
#     class Meta:
#         model = AnnexureImage
#         fields = ["id", "image", "uploaded_at"]
#         read_only_fields = ["uploaded_at"]


# class AnnexureSerializer(AliasModelSerializer):
#     images = AnnexureImageSerializer(many=True, read_only=True)

#     class Meta:
#         model = Annexure
#         fields = ["id", "name", "description", "images"]

class AnnexureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Annexure
        fields = ["id", "name", "description", "category", "image"]
        
class WorkCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkCategory
        fields = ['id', 'name', 'code', 'description', 'fitout_request']

    def validate_fitout_request(self, value):
        if isinstance(value, str):
            raise serializers.ValidationError("fitout_request must be an integer ID")
        return value



# class FitoutCategorySerializer(serializers.ModelSerializer):
#     file = serializers.FileField(write_only=True, required=True)
#     class Meta:
#         model = WorkCategory
#         fields = ["id", "name", "description", "file"]
        
#     def create(self, validated_data):
#         file = validated_data.pop("file")
#         category = WorkCategory.objects.create(**validated_data)
        
#         annexure_name = f"{category.name} File"
#         annexure = Annexure.objects.create(name=annexure_name)

#         CategoryAnnexure.objects.create(
#             category=category,
#             annexure=annexure,
#             file=file
#         )
#         return category
    
    
class SubCategorySerializer(AliasModelSerializer):
    class Meta:
        model = SubCategory
        fields = ["id", "category", "name", "code", "description"]    


class FitoutGuideSerializer(serializers.ModelSerializer):
    class Meta:
        model = FitoutGuide
        fields = ["id", "title", "file"]


# ---------------- FitOut Annexure ----------------
# class AnnexureSerializer(serializers.ModelSerializer):
#     category = serializers.CharField(source="annexure.name", read_only=True)

#     class Meta:
#         model = Annexure
#         fields = ["id",, "file", "category"]

#     def create(self, validated_data):
#         obj = Annexure(**validated_data)
#         obj.full_clean(validate_unique=False)
#         obj.save()
#         return obj

#     def update(self, instance, validated_data):
#         for attr, value in validated_data.items():
#             setattr(instance, attr, value)
#         instance.save()
#         return instance


# ---------------- FitOut Request ----------------
class FitOutRequestSerializer(serializers.ModelSerializer):
    fitout_annexures = AnnexureSerializer(many=True, required=False)
    fitout_category = serializers.PrimaryKeyRelatedField(
        queryset=WorkCategory.objects.all(), allow_null=True, required=False
    )
    work_category = serializers.PrimaryKeyRelatedField(
        queryset=WorkCategory.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = FitoutRequest
        fields = [
            "id",
            "tower",
            "flat",
            "floor",
            "oneBHK",
            "twoBHK",
            "oneBHK_RK",
            "twoBHK_TERRIS",
            "oneBHK_again",
            "description",
            "fitout_category",
            "work_category",
            "fitout_annexures",
        ]

    def create(self, validated_data):
        annexures_data = validated_data.pop("fitout_annexures", [])
        instance = FitoutRequest.objects.create(**validated_data)

        for annexure_data in annexures_data:
            annexure_obj = Annexure.objects.create(
                fitout=instance,
                annexure=annexure_data["annexure"],
                file=annexure_data.get("file")
            )

            # Ensure FitoutCategory exists for this annexure
            category, _ = WorkCategory.objects.get_or_create(
                name=annexure_obj.annexure.name,
                defaults={"description": annexure_obj.annexure.description or ""}
            )

            # Create checklist linked to FitoutCategory (FK)
            instance.checklists.create(
                name=f"{annexure_obj.annexure.name} Checklist",
                category=category,
                sub_category="",
                status=False
            )

        return instance

    def update(self, instance, validated_data):
        annexures_data = validated_data.pop("fitout_annexures", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if annexures_data is not None:
            instance.fitout_annexures.all().delete()
            instance.checklists.all().delete()

            for annexure_data in annexures_data:
                annexure_obj = Annexure.objects.create(
                    fitout=instance,
                    annexure=annexure_data["annexure"],
                    file=annexure_data.get("file")
                )

                category, _ = WorkCategory.objects.get_or_create(
                    name=annexure_obj.annexure.name,
                    defaults={"description": annexure_obj.annexure.description or ""}
                )

                instance.checklists.create(
                    name=f"{annexure_obj.annexure.name} Checklist",
                    category=category,
                    sub_category="",
                    status=False
                )

        return instance
    
    


class FitoutTypeSerializer(serializers.ModelSerializer):
    # Optional: if you want move-in options exposed for frontend dropdown
    movein_status_options = serializers.ListField(
        child=serializers.CharField(), required=False
    )

    class Meta:
        model = FitoutType
        fields = [
            "id",
            "name",
            "code",
            "flat_type",
            "base_price",
            "description",
            "status",
            "movein_date",
            "approved_by",
            "remarks",
            "gate_pass_number",
            "movein_status",
            "movein_status_options",
        ]

    def create(self, validated_data):
        # Handle move-in options separately if provided
        movein_options = validated_data.pop("movein_status_options", None)

        instance = FitoutType.objects.create(**validated_data)

        if movein_options is not None:
            instance.movein_status_options = movein_options
            instance.save()

        return instance

    def update(self, instance, validated_data):
        movein_options = validated_data.pop("movein_status_options", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if movein_options is not None:
            instance.movein_status_options = movein_options
            instance.save()

        return instance
    


# ---------------- Status & Deviation ----------------
class StatusSerializer(AliasModelSerializer):
    class Meta:
        model = Status
        fields = "__all__"


class DeviationStatusSerializer(AliasModelSerializer):
    class Meta:
        model = DeviationStatus
        fields = "__all__"


class FitoutDeviationImageSerializer(AliasModelSerializer):
    class Meta:
        model = FitoutDeviationImage
        fields = ["id", "image", "deviation", "uploaded_at"]
        read_only_fields = ["uploaded_at"]


class FitoutDeviationChatSerializer(AliasModelSerializer):
    deviation = serializers.PrimaryKeyRelatedField(queryset=FitoutDeviation.objects.all())

    class Meta:
        model = FitoutDeviationChat
        fields = ["id", "message", "sender_id", "file", "timestamp", "deviation"]
        read_only_fields = ["timestamp"]


class FitoutDeviationSerializer(AliasModelSerializer):
    images = FitoutDeviationImageSerializer(many=True, required=False)
    chats = FitoutDeviationChatSerializer(many=True, required=False)
    status_name = serializers.CharField(source='status.status', read_only=True)
    fitout_request = serializers.PrimaryKeyRelatedField(queryset=FitoutRequest.objects.all())

    class Meta:
        model = FitoutDeviation
        fields = [
            "id",
            "penalty_amount",
            "status",
            "status_name",
            "fitout_request",
            "discription", 
            "images",
            "chats"
        ]
        read_only_fields = []
        
        
class PaymentModeSerializer(serializers.ModelSerializer):
    fitout_requests_count = serializers.IntegerField(
        source="fitout_requests.count", read_only=True
    )

    class Meta:
        model = PaymentMode
        fields = [
            "id",                                                                                       
            "name",
            "description",
            "is_active",
            "fitout_requests_count"
        ]
        read_only_fields = ["fitout_requests_count"]        


# ---------------- Fitout Request Chat ----------------
class FitoutRequestChatSerializer(AliasModelSerializer):
    class Meta:
        model = FitoutRequestChat
        fields = ["id", "message", "sender_id", "file", "timestamp"]
        read_only_fields = ["timestamp"]


# ---------------- Checklist & Answers ----------------
# class AssociationSerializer(AliasModelSerializer):
#     class Meta:
#         model = Association
#         fields = ["id", "fitout_request", "user_ids"]


class QuestionOptionSerializer(AliasModelSerializer):
    question = serializers.PrimaryKeyRelatedField(queryset=ChecklistQuestion.objects.all())
    class Meta:
        model = QuestionOption
        fields = ["id", "option_text", "is_correct", "question"]


class ChecklistQuestionSerializer(AliasModelSerializer):
    options = QuestionOptionSerializer(many=True, required=False)
    checklist = serializers.PrimaryKeyRelatedField(queryset=FitoutChecklist.objects.all())

    class Meta:
        model = ChecklistQuestion
        fields = ["id", "question_text", "answer_type", "is_mandatory", "photo_required", "options", "checklist"]


class FitoutChecklistSerializer(AliasModelSerializer):
    questions = ChecklistQuestionSerializer(many=True, required=False)

    class Meta:
        model = FitoutChecklist
        fields = [
            "id",
            "fitout_request",
            "name",
            "status",
            "work_category",
            "sub_category",
            "associations",
            "questions"
        ]


class ChecklistAnswerSerializer(AliasModelSerializer):
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    question_type = serializers.CharField(source='question.answer_type', read_only=True)
    selected_option_text = serializers.CharField(source='selected_option.option_text', read_only=True)
    fitout_request = serializers.PrimaryKeyRelatedField(queryset=FitoutRequest.objects.all())
    question = serializers.PrimaryKeyRelatedField(queryset=ChecklistQuestion.objects.all())
    selected_option = serializers.PrimaryKeyRelatedField(queryset=QuestionOption.objects.all(), required=False, allow_null=True)

    class Meta:
        model = ChecklistAnswer
        fields = [
            "id",
            "fitout_request",
            "question",
            "question_text",
            "question_type",
            "answer_text",
            "selected_option",
            "selected_option_text",
            "photo"
        ]


class FitoutGuideSerializer(AliasModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = FitoutGuide
        fields = ["id", "title", "description", "file", "category", "category_name"]
        read_only_fields = ["id", "category_name"]

    def create(self, validated_data):
        alias = self.alias
        obj = FitoutGuide.objects.using(alias).create(**validated_data)
        return obj

    def update(self, instance, validated_data):
        alias = self.alias
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(using=alias)
        return instance