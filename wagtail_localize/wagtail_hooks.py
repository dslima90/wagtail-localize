from django.conf.urls import url, include
from django.templatetags.static import static
from django.urls import path
from django.utils.html import format_html_join
from django.views.i18n import JavaScriptCatalog

from wagtail.core import hooks
from wagtail.core.models import TranslatableMixin

from . import admin_views
from .models import Translation
from .views.edit_translation import edit_translation


@hooks.register("insert_editor_js")
def insert_editor_js():
    js_files = ["wagtail_localize/js/page-editor.js"]
    return format_html_join(
        "\n",
        '<script src="{0}"></script>',
        ((static(filename),) for filename in js_files),
    )


@hooks.register("register_admin_urls")
def register_admin_urls():
    urls = [
        path('jsi18n/', JavaScriptCatalog.as_view(packages=['wagtail_localize']), name='javascript_catalog'),
        url(r"^translations_list/(\d+)/$", admin_views.translations_list_modal, name="translations_list_modal"),
    ]

    return [
        url(
            r"^localize/",
            include(
                (urls, "wagtail_localize"),
                namespace="wagtail_localize",
            ),
        )
    ]


@hooks.register("before_edit_page")
def before_edit_page(request, page):
    # Overrides the edit page view if the page is the target of a translation
    try:
        translation = Translation.objects.get(object_id=page.translation_key, target_locale_id=page.locale_id, enabled=True)
        return edit_translation(request, translation, page)

    except Translation.DoesNotExist:
        pass


@hooks.register("before_edit_snippet")
def before_edit_page(request, instance):
    # Overrides the edit snippet view if the snippet is translatable and the target of a translation
    if isinstance(instance, TranslatableMixin):
        try:
            translation = Translation.objects.get(object_id=instance.translation_key, target_locale_id=instance.locale_id, enabled=True)
            return edit_translation(request, translation, instance)

        except Translation.DoesNotExist:
            pass
