from django.db import models
from django.utils import timezone
from django.utils.text import  slugify
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.fields import ArrayField
from django.db.models import JSONField



# ---------------- Base (with soft delete + audit) ----------------
class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class DeletedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=True)


class BaseModel(models.Model):
    id = models.BigAutoField(primary_key=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by_id = models.BigIntegerField(null=True, blank=True)
    updated_by_id = models.BigIntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    # soft-delete
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by_id = models.BigIntegerField(null=True, blank=True)

    objects = ActiveManager()
    deleted_objects = DeletedManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, user_id=None):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        if user_id:
            self.deleted_by_id = user_id
        self.save(
            update_fields=["is_deleted", "deleted_at", "deleted_by_id", "updated_at"]
        )

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)


# ---------------- Core Fitout Models ----------------




class WorkCategory(BaseModel):
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True, null=True, blank=True)  # e.g. 'mech', 'civil'
    fitout_request = models.ForeignKey("FitOutRequest", on_delete=models.CASCADE, related_name="work_categories", null=True,
    blank=True)
    # tower_id = models.BigIntegerField(default=0)
    # flat_id = models.BigIntegerField(default=0)
    # # floor_id = models.BigIntegerField()
    
    
    # oneBHK = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # twoBHK = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # oneBHK_RK = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # twoBHK_TERRIS = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # oneBHK_again = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)



    description = models.TextField(blank=True, null=True)
    def save(self, *args, **kwargs):
        if not self.code:
            self.code = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class SubCategory(BaseModel):
    WorkCategory  = models.ForeignKey(WorkCategory, on_delete=models.CASCADE, related_name="subcategories")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)  # e.g. 'mech', 'civil'
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.category.name} - {self.name}"    
    
    
class Annexure(BaseModel):
    WorkCategory = models.ForeignKey(WorkCategory, on_delete=models.CASCADE, related_name="Annexures",null=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    # category = models.CharField(max_length=100, blank=True, null=True)
    image = models.ImageField(upload_to="annexure_images/", blank=True, null=True)

   
    def __str__(self):
        return self.name
  



class FitoutRequest(BaseModel):
    user_id = models.BigIntegerField(default=0)
    requester_name = models.CharField(max_length=100, default="")
    contact = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(default="", blank=True, null=True)
    # tower_id = models.BigIntegerField(default=0)
    # flat_id = models.BigIntegerField(default=0)
    # floor_id = models.BigIntegerField()
    
    
    # oneBHK = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # twoBHK = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # oneBHK_RK = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # twoBHK_TERRIS = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # oneBHK_again = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)


    scope = models.TextField(help_text="Description of renovation scope", default="no description was provided")
    preferred_start_date = models.DateField(null=True, blank=True)
    preferred_end_date = models.DateField(null=True, blank=True)

    agree_guidelines = models.BooleanField(default=False)
    refund_date = models.DateField(blank=True, null=True)
    requested_date = models.DateField(blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)

    # master_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default="PAY_AT_SITE")


    # Dynamic status field
   

    approved_by = models.BigIntegerField(blank=True, null=True)
    approval_date = models.DateTimeField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    # payment_mode = models.ForeignKey("PaymentMode", on_delete=models.SET_NULL, null=True, blank=True, related_name="fitout_requests")

    def approve(self, user_name, description=""):
        approved_status = Status.objects.filter(name__iexact="Approved").first()
        if approved_status:
            self.status = approved_status
        self.approved_by = user_name
        self.approval_date = timezone.now()
        self.description = description
        self.save()

    def reject(self, user_name, description=""):
        rejected_status = Status.objects.filter(name__iexact="Rejected").first()
        if rejected_status:
            self.status = rejected_status
        self.approved_by = user_name
        self.approval_date = timezone.now()
        self.description = description
        self.save()

    def __str__(self):
        return f"Fitout Request for Flat {self.flat.number} ({self.requester_name})"
    
    
class PaymentMode(BaseModel):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name    





class Status(BaseModel):
    name = models.CharField(max_length=50, unique=True,blank=True)
    order = models.IntegerField(help_text="Defines display order of statuses.")
    color = models.CharField(
        max_length=7, help_text="Hex color code, e.g. #00FF00", default="#000000"
    )
    is_fixed = models.BooleanField(
        default=False, help_text="Mark as fixed system status"
    )

    class Meta: 
        ordering = ["order"]
        db_table = 'api_status'

    def __str__(self):
        return self.name


class DeviationStatus(BaseModel):
    order = models.PositiveIntegerField(help_text="Defines display order of statuses.")
    name = models.CharField(max_length=100,  unique=True, help_text="Status name (e.g. Open, Resolved, Closed)")
    code = models.SlugField(max_length=100, unique=True, default="open",help_text="Unique code for internal reference (e.g. open, in_progress)")
    color = models.CharField(max_length=7, help_text="Hex color code for UI display (e.g. #FF5733)")
    is_fixed = models.BooleanField(default=False, help_text="Mark system default statuses that should not be deleted.")
    fitout_deviation = models.ForeignKey("FitoutDeviation", on_delete=models.CASCADE, related_name="deviation_statuses", null=True, blank=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "Deviation Status"
        verbose_name_plural = "Deviation Statuses"

    def __str__(self):
        return f"{self.order}. {self.name}"


class FitoutDeviation(BaseModel):
    penalty_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.ForeignKey(DeviationStatus, on_delete=models.SET_NULL, null=True, related_name="deviations")
    fitout_request = models.ForeignKey(FitoutRequest, on_delete=models.CASCADE, related_name="deviations")
    discription = models.TextField(blank=True, null=True)
    
    
class FitoutDeviationImage(models.Model):
    deviation = models.ForeignKey(FitoutDeviation, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="deviation/images/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for Deviation {self.deviation.id}"
    
 

class FitoutDeviationChat(BaseModel):
    deviation = models.ForeignKey(FitoutDeviation, on_delete=models.CASCADE, related_name="chats")
    message = models.TextField()
    sender_id = models.BigIntegerField()
    file = models.FileField(upload_to="deviation_chats/", blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message by {self.sender_id} on {self.timestamp}"


class FitoutRequestChat(BaseModel):
    fitout_request = models.ForeignKey(FitoutRequest, on_delete=models.CASCADE, related_name="chats")
    message = models.TextField(blank=True, null=True)
    sender_id = models.BigIntegerField()
    file = models.FileField(upload_to="fitout_request_chats/", blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message by {self.sender_id} on {self.timestamp}"
    
    
    
    
    
class FitoutType(models.Model):
    # --- Basic Fitout Type Details ---
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    flat_type = models.CharField(max_length=100)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    status = models.BooleanField(default=True)

    # --- Move-In Section (inside same model) ---
    movein_date = models.DateField(blank=True, null=True)
    approved_by = models.CharField(max_length=100, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    gate_pass_number = models.CharField(max_length=50, blank=True, null=True, unique=True)

    # 🔹 Dynamic Move-In Status stored inside this model
    movein_status = models.CharField(max_length=50, blank=True, null=True)
    movein_status_options = models.JSONField(
        default=list, blank=True,
        help_text="List of possible move-in statuses, e.g., ['PENDING','APPROVED','REJECTED','MOVED_IN']"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fitout_types'
        verbose_name = 'Fitout Type'
        verbose_name_plural = 'Fitout Types'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.flat_type})"

    def save(self, *args, **kwargs):
        # Auto-generate gate pass number if approved or moved in
        if self.movein_status and self.movein_status.upper() in ['APPROVED','MOVED_IN'] and not self.gate_pass_number:
            self.gate_pass_number = f"GP-{self.code}-{timezone.now().year}"
        super().save(*args, **kwargs)    
    


# ---------------- Checklist Models ----------------
class FitoutChecklist(BaseModel):
    fitout_request = models.ForeignKey(FitoutRequest, on_delete=models.CASCADE, related_name="checklists",null=True, blank=True)
    name = models.CharField(max_length=255)
    status = models.BooleanField(default=False)
    work_category = models.ForeignKey(WorkCategory, on_delete=models.CASCADE, related_name="fitout_checklists", null=True, blank=True)
    sub_category = models.ForeignKey("SubCategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="fitout_checklists")
    # associations = models.CharField(max_length=255, blank=True, null=True)


    
    def __str__(self):
        return f"{self.name} - ({'Active' if self.status else 'Inactive'})"


class ChecklistQuestion(BaseModel):
    class AnswerType(models.TextChoices):
        TEXT = "text", "Text"
        YES_NO = "yes_no", "Yes/No"
        MULTIPLE_CHOICE = "multiple_choice", "Multiple Choice"

    checklist = models.ForeignKey(FitoutChecklist, on_delete=models.CASCADE, related_name="questions")
    question_text = models.TextField()
    answer_type = models.CharField(max_length=20, choices=AnswerType.choices, default=AnswerType.TEXT)
    is_mandatory = models.BooleanField(default=False)
    photo_required = models.BooleanField(default=False)

    def __str__(self):
        return f"Q: {self.question_text[:50]}.."


class QuestionOption(BaseModel):
    question = models.ForeignKey(ChecklistQuestion, on_delete=models.CASCADE, related_name="options")
    option_text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.option_text


# ---------------- Checklist Answer Storage ----------------
class ChecklistAnswer(BaseModel):
    """Stores answers for each checklist question per request"""
    fitout_request = models.ForeignKey(FitoutRequest, on_delete=models.CASCADE, related_name="checklist_answers")
    question = models.ForeignKey(ChecklistQuestion, on_delete=models.CASCADE, related_name="checklist_answers")
    question_option = models.ForeignKey(QuestionOption, on_delete=models.CASCADE, related_name="checklist_answers", null=True, blank=True)  # if applicable

    # actual responses
    answer_text = models.TextField(blank=True, null=True)  # for TEXT type
    # selected_option = models.ForeignKey(QuestionOption, on_delete=models.SET_NULL, null=True, blank=True)  # for yes/no & MCQ
    photo = models.ImageField(upload_to="checklist_answers/photos/", blank=True, null=True)

    def __str__(self):
        return f"Answer to {self.question} for Request {self.fitout_request_id}"


# ---------------- Signals ----------------
@receiver(post_save, sender=ChecklistQuestion)
def create_yes_no_options(sender, instance, created, **kwargs):
    """Auto-create Yes/No options if answer_type is YES_NO"""
    if created and instance.answer_type == ChecklistQuestion.AnswerType.YES_NO:
        if not instance.options.exists():
            QuestionOption.objects.bulk_create([
                QuestionOption(question=instance, option_text="Yes", is_correct=False),
                QuestionOption(question=instance, option_text="No", is_correct=False),
            ])
            
            
            
class FitoutGuide(BaseModel):
    category = models.ForeignKey("WorkCategory", on_delete=models.CASCADE, related_name="guides", null=True, blank=True)

    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="fitout_guides/")  # uploaded guide file
    description = models.TextField(blank=True, null=True)  # optional description

    def __str__(self):
        return self.title
                

# class CategoryAnnexure(BaseModel):
#     category = models.ForeignKey("WorkCategory", on_delete=models.CASCADE, related_name="annexures")
#     annexure = models.ForeignKey("Annexure", on_delete=models.CASCADE, related_name="category_annexures")
#     file = models.FileField(upload_to="category_annexures/")

#     def save(self, *args, **kwargs):
#         if not self.annexure:
#             annexure_name = f"{self.category.name} File"
#             annexure = Annexure.objects.create(name=annexure_name)
#             self.annexure = annexure
#         super().save(*args, **kwargs)


    
    
    # class AnnexureImage(models.Model):
#     annexure = models.ForeignKey(Annexure, related_name="images", on_delete=models.CASCADE)
#     image = models.ImageField(upload_to="annexures/images/")
#     uploaded_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"Image for {self.annexure.name}"


# class FitOutRequest(BaseModel):
#     STATUS_CHOICES = [
#         ("PENDING", "Pending"),
#         ("APPROVED", "Approved"),
#         ("REJECTED", "Rejected"),
#     ]
    

#     PAYMENT_MODES = [
#         ("PAY_AT_SITE", "Pay at Site"),
#         ("ONLINE", "Online"),
#     ]
    
#     fitout_category = models.ForeignKey("FitoutCategory", on_delete=models.SET_NULL, null=True, blank=True)
#     annexure = models.ForeignKey(Annexure, on_delete=models.SET_NULL, null=True, blank=True)
#     work_category = models.ForeignKey(WorkCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="fitout_requests")

#     tower_id = models.BigIntegerField()
#     flat_id = models.BigIntegerField()
#     floor_id = models.BigIntegerField()
    
    
#     oneBHK = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
#     twoBHK = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
#     oneBHK_RK = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
#     twoBHK_TERRIS = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
#     oneBHK_again = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

#     # Flat type costs
#     unit_costs = JSONField(blank=True, null=True)

#     description = models.TextField(blank=True, null=True)
#     work_category = models.ForeignKey(
#         WorkCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="fitout_requests"
#     )

#     contractor_name = models.CharField(max_length=100, blank=True, null=True)
#     contractor_mobile = models.CharField(max_length=15, blank=True, null=True)

#     refund_date = models.DateField(blank=True, null=True)
#     requested_date = models.DateField(blank=True, null=True)
#     expiry_date = models.DateField(blank=True, null=True)

#     master_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
#     total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
#     amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
#     payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default="PAY_AT_SITE")

#     def __str__(self):
#         return f"FitOutRequest {self.id} - Tower {self.tower_id} - Flat {self.flat_id}"


# class FitOutAnnexure(BaseModel):
#     fitout = models.ForeignKey(FitOutRequest, on_delete=models.CASCADE)
#     Annexure = models.ForeignKey(Annexure, on_delete=models.CASCADE)
#     file = models.FileField(upload_to="fitout_annexures/", blank=True, null=True)

#     def __str__(self):
#         return f"{self.fitout} - {self.Annexure.name}"


# class Status(BaseModel):
#     order = models.IntegerField()
#     status = models.CharField(max_length=50)
#     fixed_state = models.CharField(
#         max_length=20,
#         choices=[
#             ("Pending", "Pending"),
#             ("In Progress", "In Progress"),
#             ("Completed", "Completed"),
#             ("Cancelled", "Cancelled"),
#         ],
       
#     )
#     color = models.CharField(max_length=7)


# class DeviationStatus(BaseModel):
#     order = models.PositiveIntegerField()
#     status = models.CharField(max_length=255, unique=True)
#     fixed_state = models.CharField(
#         max_length=100,
#         choices=[
#             ("open", "Open"),
#             ("in_progress", "In Progress"),
#             ("resolved", "Resolved"),
#             ("closed", "Closed"),
#         ],
#         blank=True,
#         null=True,
#     )
#     color = models.CharField(max_length=7)

#     class Meta:
#         ordering = ["order"]

#     def __str__(self):
#         return f"{self.order}. {self.status}"


# class FitoutCategory(BaseModel):
#     name = models.CharField(max_length=100)
    
#     description = models.TextField(blank=True, null=True)

#     def __str__(self):
#         return self.name


# class Association(BaseModel):
#     fitout_request=models.ForeignKey(FitOutRequest, on_delete=models.CASCADE, related_name="associations")
    
#     user_ids = ArrayField(models.BigIntegerField())
#     def __str__(self):
#         return f"Associations for FitoutRequest {self.fitout_request.id}"


    





    

