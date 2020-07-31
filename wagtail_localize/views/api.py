from rest_framework import fields, generics, serializers
from wagtail.core.models import Locale

from wagtail_localize.models import Translation, TranslationSource


class LocaleSerializer(serializers.ModelSerializer):
    display_name = fields.ReadOnlyField(source='get_display_name')

    class Meta:
        model = Locale
        fields = ['language_code', 'display_name']


class TranslationSourceSerializer(serializers.ModelSerializer):
    locale = LocaleSerializer()

    def to_representation(self, source):
        data = super().to_representation(source)
        data['content_type'] = source.specific_content_type.model_class()._meta.verbose_name.title()
        return data


    class Meta:
        model = TranslationSource
        fields = ['object_repr', 'locale']


class TranslationSerializer(serializers.ModelSerializer):
    source = TranslationSourceSerializer()
    target_locale = LocaleSerializer()
    edit_url = fields.ReadOnlyField(source='get_edit_url')
    status_display = fields.ReadOnlyField(source='get_status_display')

    def to_representation(self, translation):
        data = super().to_representation(translation)
        # TODO: Find a way to annotate this on the queryset
        data['total_strings'], data['translated_strings'] = translation.get_progress()
        return data

    class Meta:
        model = Translation
        fields = ['source', 'target_locale', 'created_at', 'source_last_updated_at', 'translations_last_updated_at', 'destination_last_updated_at', 'enabled', 'edit_url', 'status_display']


class ListTranslationsView(generics.ListAPIView):
    model = Translation
    serializer_class = TranslationSerializer

    def get_queryset(self):
        translations = Translation.objects.all().order_by('created_at')

        if 'source_locale' in self.request.GET:
            translations = translations.filter(source__locale__language_code=self.request.GET['source_locale'])

        if 'target_locale' in self.request.GET:
            translations = translations.filter(target_locale__language_code=self.request.GET['target_locale'])

        return translations.select_related('source', 'source__locale', 'source__specific_content_type', 'target_locale')
