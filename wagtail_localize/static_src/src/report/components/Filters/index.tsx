import React, { FunctionComponent } from 'react';
import SelectBoxFilter from '../SelectBoxFilter';
import gettext from 'gettext';
import {LOCALES} from 'wagtailConfig';

export const FILTER_NAMES = [
    'source_locale',
    'target_locale',
];

const LOCALE_OPTIONS = LOCALES.map(({code, display_name}) => {
    return {
        value: code,
        label: display_name,
    }
});

interface FiltersProps {
    filters: Map<string, string>;
    setFilters(filters: Map<string, string>): void;
}

const Filters: FunctionComponent<FiltersProps> = ({filters, setFilters}) => {
    const setValueFunc = (fieldName: string) => {
        return (value: string) => {
            const newFilters = new Map(filters);

            if (value) {
                newFilters.set(fieldName, value);
            } else {
                newFilters.delete(fieldName);
            }

            setFilters(newFilters);
        };
    };

    return (
        <>
            <SelectBoxFilter label={gettext("Source Locale")} options={LOCALE_OPTIONS} value={filters.get('source_locale')} onChange={setValueFunc('source_locale')} />
            <SelectBoxFilter label={gettext("Target Locale")} options={LOCALE_OPTIONS} value={filters.get('target_locale')} onChange={setValueFunc('target_locale')} />
        </>
    )
};

export default Filters;
