from django.db import transaction
import polib

from wagtail_localize.models import Translation, MissingRelatedObjectError, UnknownContext, UnknwownString

from .models import SyncLog


class Importer:
    def __init__(self, logger):
        self.logger = logger
        self.log = None

    @transaction.atomic
    def import_resource(self, translation, po):
        for warning in translation.import_po(po):
            if isinstance(warning, UnknownContext):
                self.logger.warning(f"While translating '{translation.source.object_repr}' into {translation.target_locale.get_display_name()}: Unrecognised context '{warning.context}'")

            elif isinstance(warning, UnknwownString):
                self.logger.warning(f"While translating '{translation.source.object_repr}' into {translation.target_locale.get_display_name()}: Unrecognised string '{warning.string}'")

        try:
            translation.save_target()
        except MissingRelatedObjectError:
            # Ignore error if there was a missing related object
            # In this case, the translations will just be updated but the page
            # wont be updated. When the related object is translated, the user
            # can manually hit the save draft/publish button to create/update
            # this page.
            self.logger.warning(f"Unable to translate '{translation.source.object_repr}' into {translation.target_locale.get_display_name()}: Missing related object")

        self.log.add_translation(translation)

    def start_import(self, commit_id):
        self.log = SyncLog.objects.create(
            action=SyncLog.ACTION_PULL, commit_id=commit_id
        )

    def import_file(self, filename, old_content, new_content):
        self.logger.info(f"Pull: Importing changes in file '{filename}'")
        po = polib.pofile(new_content.decode("utf-8"))
        translation = Translation.objects.get(uuid=po.metadata['X-WagtailLocalize-TranslationID'])
        self.import_resource(translation, po)
