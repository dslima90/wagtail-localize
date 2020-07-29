from urllib.parse import urlencode

from django.conf.urls import url, include
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.templatetags.static import static
from django.utils.html import format_html_join
from django.utils.translation import gettext as _

from wagtail.admin import widgets as wagtailadmin_widgets
from wagtail.core import hooks

from . import admin_views
from .views import submit_translations


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
        url(r"^translations_list/(\d+)/$", admin_views.translations_list_modal, name="translations_list_modal"),
        url(r"^submit/page/(\d+)/$", submit_translations.submit_page_translation, name="submit_page_translation"),
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


@hooks.register('register_permissions')
def register_submit_translation_permission():
    return Permission.objects.filter(content_type__app_label='wagtail_localize', codename='submit_translation')


@hooks.register("register_page_listing_more_buttons")
def page_listing_more_buttons(page, page_perms, is_parent=False, next_url=None):
    if page_perms.user.has_perms(['wagtail_localize.submit_translation']):
        url = reverse("wagtail_localize:submit_page_translation", args=[page.id])
        if next_url is not None:
            url += '?' + urlencode({'next': next_url})

        yield wagtailadmin_widgets.Button(_("Translate this page"), url, priority=60)
