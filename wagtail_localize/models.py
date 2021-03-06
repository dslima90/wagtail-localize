import json
import uuid
from collections import defaultdict

import polib
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models import (
    Case,
    When,
    Value,
    IntegerField,
    Count,
    Sum,
    Subquery,
    Exists,
    OuterRef
)
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _
from modelcluster.models import (
    ClusterableModel,
    get_serializable_data_for_fields,
    model_from_serializable_data,
)
from wagtail.core.models import Page

from .segments import StringSegmentValue, TemplateSegmentValue, RelatedObjectSegmentValue
from .segments.extract import extract_segments
from .segments.ingest import ingest_segments
from .strings import StringValue


def pk(obj):
    if isinstance(obj, models.Model):
        return obj.pk
    else:
        return obj


class TranslatableObjectManager(models.Manager):
    def get_or_create_from_instance(self, instance):
        return self.get_or_create(
            translation_key=instance.translation_key,
            content_type=ContentType.objects.get_for_model(
                instance.get_translation_model()
            ),
        )

    def get_for_instance(self, instance):
        return self.get(
            translation_key=instance.translation_key,
            content_type=ContentType.objects.get_for_model(
                instance.get_translation_model()
            ),
        )


class TranslatableObject(models.Model):
    """
    Represents something that can be translated.

    Note that one instance of this represents all translations for the object.
    """

    translation_key = models.UUIDField(primary_key=True)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, related_name="+"
    )

    objects = TranslatableObjectManager()

    def has_translation(self, locale):
        return self.content_type.get_all_objects_for_this_type(
            translation_key=self.translation_key, locale_id=pk(locale)
        ).exists()

    def get_instance(self, locale):
        return self.content_type.get_object_for_this_type(
            translation_key=self.translation_key, locale_id=pk(locale)
        )

    def get_instance_or_none(self, locale):
        try:
            return self.get_instance(locale)
        except self.content_type.model_class().DoesNotExist:
            pass

    class Meta:
        unique_together = [("content_type", "translation_key")]


class SourceDeletedError(Exception):
    pass


class CannotSaveDraftError(Exception):
    """
    Raised when a save draft was request on a non-page model.
    """
    pass


class MissingTranslationError(Exception):
    def __init__(self, segment, locale):
        self.segment = segment
        self.locale = locale

        super().__init__()


class MissingRelatedObjectError(Exception):
    def __init__(self, segment, locale):
        self.segment = segment
        self.locale = locale

        super().__init__()


class TranslationSourceQuerySet(models.QuerySet):
    def get_for_instance(self, instance):
        object = TranslatableObject.objects.get_for_instance(
            instance
        )
        return self.filter(
            object=object,
            locale=instance.locale,
        )


class TranslationSource(models.Model):
    """
    A piece of content that to be used as a source for translations.
    """

    object = models.ForeignKey(
        TranslatableObject, on_delete=models.CASCADE, related_name="sources"
    )
    # object.content_type refers to the model that the TranslatableMixin was added to, however that model
    # might have child models. So specific_content_type is needed to refer to the content type that this
    # source data was extracted from.
    specific_content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, related_name="+"
    )
    locale = models.ForeignKey("wagtailcore.Locale", on_delete=models.CASCADE)
    object_repr = models.TextField(max_length=200)
    content_json = models.TextField()
    created_at = models.DateTimeField()

    objects = TranslationSourceQuerySet.as_manager()

    @classmethod
    def from_instance(cls, instance, force=False):
        # Make sure we're using the specific version of pages
        if isinstance(instance, Page):
            instance = instance.specific

        object, created = TranslatableObject.objects.get_or_create_from_instance(
            instance
        )

        if isinstance(instance, ClusterableModel):
            content_json = instance.to_json()
        else:
            serializable_data = get_serializable_data_for_fields(instance)
            content_json = json.dumps(serializable_data, cls=DjangoJSONEncoder)

        if not force:
            # Check if the instance has changed at all since the previous revision
            previous_revision = object.sources.order_by("created_at").last()
            if previous_revision:
                if json.loads(content_json) == json.loads(
                    previous_revision.content_json
                ):
                    return previous_revision, False

        return (
            cls.objects.create(
                object=object,
                specific_content_type=ContentType.objects.get_for_model(instance.__class__),
                locale=instance.locale,
                object_repr=str(instance)[:200],
                content_json=content_json,
                created_at=timezone.now(),
            ),
            True,
        )

    def get_source_instance(self):
        """
        This gets the live version of instance that the source data was extracted from.

        This is different to source.object.get_instance(source.locale) as the instance
        returned by this methid will have the same model that the content was extracted
        from. The model returned by `object.get_instance` might be more generic since
        that model only records the model that the TranslatableMixin was applied to but
        that model might have child models.
        """
        return self.specific_content_type.get_object_for_this_type(
            translation_key=self.object_id, locale_id=self.locale_id
        )

    def get_translated_instance(self, locale):
        return self.specific_content_type.get_object_for_this_type(
            translation_key=self.object_id, locale_id=pk(locale)
        )

    def as_instance(self):
        """
        Builds an instance of the object with the content at this revision.
        """
        try:
            instance = self.get_source_instance()
        except models.ObjectDoesNotExist:
            raise SourceDeletedError

        if isinstance(instance, Page):
            return instance.with_content_json(self.content_json)

        elif isinstance(instance, ClusterableModel):
            new_instance = instance.__class__.from_json(self.content_json)

        else:
            new_instance = model_from_serializable_data(
                instance.__class__, json.loads(self.content_json)
            )

        new_instance.pk = instance.pk
        new_instance.locale = instance.locale
        new_instance.translation_key = instance.translation_key

        return new_instance

    def extract_segments(self):
        for segment in extract_segments(self.as_instance()):
            if isinstance(segment, TemplateSegmentValue):
                TemplateSegment.from_value(self, segment)
            elif isinstance(segment, RelatedObjectSegmentValue):
                RelatedObjectSegment.from_value(self, segment)
            else:
                StringSegment.from_value(self, self.locale, segment)

    def export_po(self):
        """
        Exports a PO file contining the source strings.
        """
        # Get messages
        messages = defaultdict(list)

        for string_segment in StringSegment.objects.filter(source=self).order_by('order').select_related("context", "string"):
            messages[string_segment.string.data] = string_segment.context.path

        # Build a PO file
        po = polib.POFile(wrapwidth=200)
        po.metadata = {
            "POT-Creation-Date": str(timezone.now()),
            "MIME-Version": "1.0",
            "Content-Type": "text/plain; charset=utf-8",
        }

        for text, context in messages.items():
            po.append(
                polib.POEntry(
                    msgid=text,
                    msgctxt=context,
                    msgstr="",
                )
            )

        return po

    @transaction.atomic
    def create_or_update_translation(self, locale, user=None, publish=True, copy_parent_pages=False, string_translation_fallback_to_source=False):
        """
        Creates/updates a translation of the object into the specified locale
        based on the content of this source and the translated strings
        currently in translation memory.
        """
        original = self.as_instance()
        created = False

        # Only pages can be saved as draft
        if not publish and not isinstance(original, Page):
            raise CannotSaveDraftError

        try:
            translation = self.get_translated_instance(locale)
        except models.ObjectDoesNotExist:
            if isinstance(original, Page):
                translation = original.copy_for_translation(locale, copy_parents=copy_parent_pages)
            else:
                translation = original.copy_for_translation(locale)

            created = True

        # Copy synchronised fields
        for field in getattr(translation, 'translatable_fields', []):
            if field.is_synchronized(original):
                # TODO: Use Django to set the field so the attname is correct
                setattr(
                    translation, field.field_name, getattr(original, field.field_name)
                )

        # Fetch all translated segments
        string_segments = (
            StringSegment.objects.filter(source=self)
            .annotate_translation(locale)
            .select_related("context", "string")
        )

        template_segments = (
            TemplateSegment.objects.filter(source=self)
            .select_related("template")
            .select_related("context")
        )

        related_object_segments = (
            RelatedObjectSegment.objects.filter(source=self)
            .select_related("object")
            .select_related("context")
        )

        segments = []

        for string_segment in string_segments:
            if string_segment.translation:
                string = StringValue(string_segment.translation)
            elif string_translation_fallback_to_source:
                string = StringValue(string_segment.string.data)
            else:
                raise MissingTranslationError(string_segment, locale)

            segment_value = StringSegmentValue(
                string_segment.context.path,
                string,
                attrs=json.loads(string_segment.attrs)
            ).with_order(string_segment.order)

            segments.append(segment_value)

        for template_segment in template_segments:
            template = template_segment.template
            segment_value = TemplateSegmentValue(
                template_segment.context.path,
                template.template_format,
                template.template,
                template.string_count,
                order=template_segment.order,
            )
            segments.append(segment_value)

        for related_object_segment in related_object_segments:
            if not related_object_segment.object.has_translation(locale):
                raise MissingRelatedObjectError(related_object_segment, locale)

            segment_value = RelatedObjectSegmentValue(
                related_object_segment.context.path,
                related_object_segment.object.content_type,
                related_object_segment.object.translation_key,
                order=related_object_segment.order,
            )
            segments.append(segment_value)

        # Ingest all translated segments
        ingest_segments(original, translation, self.locale, locale, segments)

        if isinstance(translation, Page):
            # Make sure the slug is valid
            translation.slug = slugify(translation.slug)
            translation.save()

            # Create a new revision
            page_revision = translation.save_revision(user=user)

            if publish:
                page_revision.publish()
        else:
            translation.save()
            page_revision = None

        # Log that the translation was made
        TranslationLog.objects.create(
            source=self, locale=locale, page_revision=page_revision
        )

        return translation, created


class POImportWarning:
    """
    Base class for warnings that are yielded by Translation.import_po.
    """
    pass


class UnknownString(POImportWarning):
    def __init__(self, index, string):
        self.index = index
        self.string = string

    def __eq__(self, other):
        return isinstance(other, UnknownString) and self.index == other.index and self.string == other.string

    def __repr__(self):
        return f"<UnknownString {self.index} '{self.string}'>"


class UnknownContext(POImportWarning):
    def __init__(self, index, context):
        self.index = index
        self.context = context

    def __eq__(self, other):
        return isinstance(other, UnknownContext) and self.index == other.index and self.context == other.context

    def __repr__(self):
        return f"<UnknownContext {self.index} '{self.context}'>"


class StringNotUsedInContext(POImportWarning):
    def __init__(self, index, string, context):
        self.index = index
        self.string = string
        self.context = context

    def __eq__(self, other):
        return isinstance(other, StringNotUsedInContext) and self.index == other.index and self.string == other.string and self.context == other.context

    def __repr__(self):
        return f"<StringNotUsedInContext {self.index} '{self.string}' '{self.context}'>"


class Translation(models.Model):
    """
    Manages the translation of an object into a locale.
    An instance of this model is created whenever something is submitted for translation
    into a new language. They live until either the source or destination has been deleted.
    Only one of these will exist for a given object/langauge. If the object is resubmitted
    for translation, the existing Translation instance's 'source' field is updated.
    """
    # A unique ID that can be used to reference this request in external systems
    uuid = models.UUIDField(unique=True, default=uuid.uuid4)

    object = models.ForeignKey(
        TranslatableObject, on_delete=models.CASCADE, related_name="translations"
    )
    target_locale = models.ForeignKey(
        "wagtailcore.Locale",
        on_delete=models.CASCADE,
        related_name="translations",
    )

    # Note: The source may be changed if the object is resubmitted for translation into the same locale
    source = models.ForeignKey(
        TranslationSource, on_delete=models.CASCADE, related_name="translations"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    source_last_updated_at = models.DateTimeField(auto_now_add=True)
    translations_last_updated_at = models.DateTimeField(null=True)
    destination_last_updated_at = models.DateTimeField(null=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = [
            ('object', 'target_locale'),
        ]

    def get_progress(self):
        """
        Returns the current progress of translating this Translation.
        Returns two integers:
        - The total number of segments in the source that need to be translated
        - The number of segments that have been translated into the locale
        """
        # Get QuerySet of Segments that need to be translated
        required_segments = StringSegment.objects.filter(source_id=self.source_id)

        # Annotate each Segment with a flag that indicates whether the segment is translated
        # into the locale
        required_segments = required_segments.annotate(
            is_translated=Exists(
                StringTranslation.objects.filter(
                    translation_of_id=OuterRef("string_id"),
                    context_id=OuterRef("context_id"),
                    locale_id=self.target_locale_id,
                )
            )
        )

        # Count the total number of segments and the number of translated segments
        aggs = required_segments.annotate(
            is_translated_i=Case(
                When(is_translated=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).aggregate(total_segments=Count("pk"), translated_segments=Sum("is_translated_i"))

        return aggs["total_segments"], aggs["translated_segments"]

    def get_status_display(self):
        """
        Returns a string to describe the current status of this translation to a user.
        """
        total_segments, translated_segments = self.get_progress()
        if total_segments == translated_segments:
            return _("Up to date")
        else:
            return _("Waiting for translations")

    def export_po(self):
        """
        Exports a PO file contining the source strings and translations.
        """
        # Get messages
        messages = defaultdict(list)

        string_segments = (
            StringSegment.objects.filter(source=self.source)
            .order_by('order')
            .select_related("context", "string")
            .annotate_translation(self.target_locale)
        )

        for string_segment in string_segments:
            messages[string_segment.string.data] = (string_segment.context.path, string_segment.translation)

        # Build a PO file
        po = polib.POFile(wrapwidth=200)
        po.metadata = {
            "POT-Creation-Date": str(timezone.now()),
            "MIME-Version": "1.0",
            "Content-Type": "text/plain; charset=utf-8",
            "X-WagtailLocalize-TranslationID": str(self.uuid),
        }

        for text, (context, translation) in messages.items():
            po.append(
                polib.POEntry(
                    msgid=text,
                    msgctxt=context,
                    msgstr=translation or "",
                )
            )

        # Add any obsolete segments that have translations for future reference
        # We find this by looking for obsolete contexts and annotate the latest
        # translation for each one. Contexts that were never translated are
        # excluded
        for translation in (
            StringTranslation.objects
            .filter(context__object=self.object, locale=self.target_locale)
            .exclude(translation_of_id__in=StringSegment.objects.filter(source=self.source).values_list('string_id', flat=True))
            .select_related("translation_of", "context")
            .iterator()
        ):
            po.append(
                polib.POEntry(
                    msgid=translation.translation_of.data,
                    msgstr=translation.data or "",
                    msgctxt=translation.context.path,
                    obsolete=True,
                )
            )

        return po

    @transaction.atomic
    def import_po(self, po, delete=False):
        """
        Imports translations from a PO file.
        """
        seen_translation_ids = set()

        if 'X-WagtailLocalize-TranslationID' in po.metadata and po.metadata['X-WagtailLocalize-TranslationID'] != str(self.uuid):
            return

        for index, entry in enumerate(po):
            try:
                string = String.objects.get(locale_id=self.source.locale_id, data=entry.msgid)
                context = TranslationContext.objects.get(object_id=self.source.object_id, path=entry.msgctxt)

                # Ignore blank strings
                if not entry.msgstr:
                    continue

                # Ignore if the string has never appeared in a version of this object
                if not StringSegment.objects.filter(string=string, context=context).exists():
                    yield StringNotUsedInContext(index, entry.msgid, entry.msgctxt)
                    continue

                string_translation, created = string.translations.get_or_create(
                    locale_id=self.target_locale_id,
                    context=context,
                    defaults={
                        "data": entry.msgstr,
                        "updated_at": timezone.now(),
                    },
                )

                seen_translation_ids.add(string_translation.id)

                if not created:
                    # Update the string_translation only if it has changed
                    if string_translation.data != entry.msgstr:
                        string_translation.data = entry.msgstr
                        string_translation.updated_at = timezone.now()
                        string_translation.save()

            except TranslationContext.DoesNotExist:
                yield UnknownContext(index, entry.msgctxt)

            except String.DoesNotExist:
                yield UnknownString(index, entry.msgid)

        # Delete any translations that weren't mentioned
        if delete:
            StringTranslation.objects.filter(context__object=self.object, locale=self.target_locale).exclude(id__in=seen_translation_ids).delete()

    def save_target(self, user=None, publish=True):
        """
        Saves the target page/snippet using the current translations.
        """
        self.source.create_or_update_translation(self.target_locale, user=user, publish=publish, string_translation_fallback_to_source=True, copy_parent_pages=True)


class TranslationLog(models.Model):
    """
    This model logs when we make a translation.
    """

    source = models.ForeignKey(
        TranslationSource, on_delete=models.CASCADE, related_name="translation_logs"
    )
    locale = models.ForeignKey(
        "wagtailcore.Locale",
        on_delete=models.CASCADE,
        related_name="translation_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    page_revision = models.ForeignKey(
        "wagtailcore.PageRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    def get_instance(self):
        """
        Gets the instance of the translated object, if it still exists.
        """
        return self.source.object.get_instance(self.locale)


class String(models.Model):
    UUID_NAMESPACE = uuid.UUID("59ed7d1c-7eb5-45fa-9c8b-7a7057ed56d7")

    locale = models.ForeignKey("wagtailcore.Locale", on_delete=models.CASCADE, related_name="source_strings")

    data_hash = models.UUIDField()
    data = models.TextField()

    @classmethod
    def get_data_hash(cls, data):
        return uuid.uuid5(cls.UUID_NAMESPACE, data)

    @classmethod
    def from_value(cls, locale, stringvalue):
        string, created = cls.objects.get_or_create(
            locale_id=pk(locale),
            data_hash=cls.get_data_hash(stringvalue.data),
            defaults={"data": stringvalue.data},
        )

        return string

    def as_value(self):
        return StringValue(self.data)

    def save(self, *args, **kwargs):
        if self.data and self.data_hash is None:
            self.data_hash = self.get_data_hash(self.data)

        return super().save(*args, **kwargs)

    class Meta:
        unique_together = [("locale", "data_hash")]


class TranslationContext(models.Model):
    object = models.ForeignKey(
        TranslatableObject, on_delete=models.CASCADE, related_name="+"
    )
    path_id = models.UUIDField()
    path = models.TextField()

    class Meta:
        unique_together = [
            ("object", "path_id"),
        ]

    @classmethod
    def get_path_id(cls, path):
        return uuid.uuid5(uuid.UUID("fcab004a-2b50-11ea-978f-2e728ce88125"), path)

    def save(self, *args, **kwargs):
        if self.path and self.path_id is None:
            self.path_id = self.get_path_id(self.path)

        return super().save(*args, **kwargs)

    def as_string(self):
        """
        Creates a string that can be used in the "msgctxt" field of PO files.
        """
        return str(self.object_id) + ":" + self.path

    @classmethod
    def get_from_string(cls, msgctxt):
        """
        Looks for the TranslationContext that the given string represents.
        """
        object_id, path = msgctxt.split(":")
        path_id = cls.get_path_id(path)
        return cls.objects.get(object_id=object_id, path_id=path_id)


class StringTranslation(models.Model):
    translation_of = models.ForeignKey(
        String, on_delete=models.CASCADE, related_name="translations"
    )
    locale = models.ForeignKey("wagtailcore.Locale", on_delete=models.CASCADE, related_name="string_translations")
    context = models.ForeignKey(
        TranslationContext,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translations",
    )
    data = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("locale", "translation_of", "context")]

    @classmethod
    def from_text(cls, translation_of, locale, context, data):
        segment, created = cls.objects.get_or_create(
            translation_of=translation_of,
            locale_id=pk(locale),
            context_id=pk(context),
            defaults={"data": data},
        )

        return segment


class Template(models.Model):
    BASE_UUID_NAMESPACE = uuid.UUID("4599eabc-3f8e-41a9-be61-95417d26a8cd")

    uuid = models.UUIDField(unique=True)
    template = models.TextField()
    template_format = models.CharField(max_length=100)
    string_count = models.PositiveIntegerField()

    @classmethod
    def from_value(cls, template_value):
        uuid_namespace = uuid.uuid5(cls.BASE_UUID_NAMESPACE, template_value.format)

        template, created = cls.objects.get_or_create(
            uuid=uuid.uuid5(uuid_namespace, template_value.template),
            defaults={
                "template": template_value.template,
                "template_format": template_value.format,
                "string_count": template_value.string_count,
            },
        )

        return template


class BaseSegment(models.Model):
    source = models.ForeignKey(TranslationSource, on_delete=models.CASCADE)
    context = models.ForeignKey(TranslationContext, on_delete=models.PROTECT,)
    order = models.PositiveIntegerField()

    class Meta:
        abstract = True


class StringSegmentQuerySet(models.QuerySet):
    def annotate_translation(self, locale):
        """
        Adds a 'translation' field to the segments containing the
        text content of the segment translated into the specified
        locale.
        """
        return self.annotate(
            translation=Subquery(
                StringTranslation.objects.filter(
                    translation_of_id=OuterRef("string_id"),
                    locale_id=pk(locale),
                    context_id=OuterRef("context_id"),
                ).values("data")
            )
        )


class StringSegment(BaseSegment):
    string = models.ForeignKey(
        String, on_delete=models.CASCADE, related_name="segments"
    )

    # When we extract the segment, we replace HTML attributes with id tags
    # The attributes that were removed are stored here. These must be
    # added into the translated strings.
    # These are stored as a mapping of element ids to KV mappings of
    # attributes in JSON format. For example:
    #
    #  For this segment: <a id="a1">Link to example.com</a>
    #
    #  The value of this field could be:
    #
    #  {
    #      "a#a1": {
    #          "href": "https://www.example.com"
    #      }
    #  }
    attrs = models.TextField(blank=True)

    objects = StringSegmentQuerySet.as_manager()

    @classmethod
    def from_value(cls, source, language, value):
        string = String.from_value(language, value.string)
        context, context_created = TranslationContext.objects.get_or_create(
            object_id=source.object_id, path=value.path,
        )

        segment, created = cls.objects.get_or_create(
            source=source,
            context=context,
            order=value.order,
            string=string,
            attrs=json.dumps(value.attrs),
        )

        return segment


class TemplateSegment(BaseSegment):
    template = models.ForeignKey(
        Template, on_delete=models.CASCADE, related_name="segments"
    )

    @classmethod
    def from_value(cls, source, value):
        template = Template.from_value(value)
        context, context_created = TranslationContext.objects.get_or_create(
            object_id=source.object_id, path=value.path,
        )

        segment, created = cls.objects.get_or_create(
            source=source,
            context=context,
            order=value.order,
            template=template,
        )

        return segment


class RelatedObjectSegment(BaseSegment):
    object = models.ForeignKey(
        TranslatableObject, on_delete=models.CASCADE, related_name="references"
    )

    @classmethod
    def from_value(cls, source, value):
        context, context_created = TranslationContext.objects.get_or_create(
            object_id=source.object_id, path=value.path,
        )

        segment, created = cls.objects.get_or_create(
            source=source,
            context=context,
            order=value.order,
            object=TranslatableObject.objects.get_or_create(
                content_type=value.content_type,
                translation_key=value.translation_key,
            )[0],
        )

        return segment
