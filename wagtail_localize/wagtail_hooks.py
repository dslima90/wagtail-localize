from django.conf.urls import url, include
from django.templatetags.static import static
from django.urls import path, reverse
from django.utils.html import format_html_join
from django.utils.translation import ugettext_lazy as _
from django.views.i18n import JavaScriptCatalog
from wagtail.admin.menu import MenuItem
from wagtail.core import hooks
from wagtail.core.models import TranslatableMixin

from . import admin_views
from .models import Translation
from .views.api import ListTranslationsView
from .views.edit_translation import edit_translation
from .views.reports import translations_report


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
    api_urls = [
        path('translations/', ListTranslationsView.as_view(), name='translations'),
    ]

    urls = [
        path('api/', include((api_urls, "api"), namespace="api")),
        path('jsi18n/', JavaScriptCatalog.as_view(packages=['wagtail_localize']), name='javascript_catalog'),
        url(r"^translations_list/(\d+)/$", admin_views.translations_list_modal, name="translations_list_modal"),
        path('reports/translations/', translations_report, name='translations_report'),
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


class TranslationsMenuItem(MenuItem):
    def is_shown(self, request):
        return True


@hooks.register("register_reports_menu_item")
def register_menu_item():
    return TranslationsMenuItem(
        _("Translations"),
        reverse("wagtail_localize:translations_report"),
        classnames="icon icon-site",
        order=500,
    )
