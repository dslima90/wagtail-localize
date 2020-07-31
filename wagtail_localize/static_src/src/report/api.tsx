// Note: These types need to exactly match the serializers in wagtail_localize/views/api.py
export interface Locale {
    language_code: string;
    display_name: string;
}

export interface TranslationSource {
    object_repr: string;
    content_type: string;
    locale: Locale;
}

export interface Translation {
    source: TranslationSource;
    target_locale: Locale;
    created_at: string;
    source_last_updated_at: string;
    translations_last_updated_at: string;
    destination_last_updated_at: string;
    enabled: boolean;
    edit_url: string|null;
    status_display: string;
    total_strings: number;
    translated_strings: number;
}
