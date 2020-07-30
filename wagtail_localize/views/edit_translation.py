import json

from django.urls import reverse
from django.shortcuts import render
from wagtail.core.models import Page

from wagtail_localize.models import Translation


def edit_translation(request, translation, instance):
    live_url = None
    if isinstance(instance, Page):
        page_perms = instance.permissions_for_user(request.user)

        if instance.live:
            live_url = instance.full_url

    return render(request, 'wagtail_localize/admin/edit_translation.html', {
        # These props are passed directly to the TranslationEditor react component
        'props': json.dumps({
            'object': {
                'title': str(instance),
                'liveUrl': live_url,
            },
            'sourceLocale': {
                'code': translation.source.locale.language_code,
                'displayName': translation.source.locale.get_display_name(),
            },
            'locale': {
                'code': translation.target_locale.language_code,
                'displayName': translation.target_locale.get_display_name(),
            },
            'translations': [
                {
                    'title': str(translated_instance),
                    'locale': {
                        'code': translated_instance.locale.language_code,
                        'displayName': translated_instance.locale.get_display_name(),
                    },
                    'editUrl': reverse('wagtailadmin_pages:edit', args=[translated_instance.id]) if isinstance(translated_instance, Page) else None,  # TODO
                }
                for translated_instance in instance.get_translations().select_related('locale')
            ],
            'perms': {
                # Only pages support saving draft
                'canSaveDraft': isinstance(instance, Page),
                'canPublish': not isinstance(instance, Page) or page_perms.can_publish(),
                'canUnpublish': isinstance(instance, Page) and page_perms.can_publish(),
                'canLock': isinstance(instance, Page) and page_perms.can_lock(),
                'canDelete': True,  # TODO
            },
            'segments': [
                {
                    'id': segment.id,
                    'contentPath': segment.context.path,
                    'source': segment.string.data,
                    'value': segment.translation or '',
                }
                for segment in translation.source.stringsegment_set.all().annotate_translation(translation.target_locale)
            ],
        })
    })
