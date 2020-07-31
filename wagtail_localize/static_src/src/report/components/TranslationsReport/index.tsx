import React, { FunctionComponent } from 'react';
import gettext from 'gettext';
import {
    parse as parseQueryString,
    stringify as stringifyQueryString,
} from 'query-string';

import Header from '../../../common/components/Header';
import Filters, { FILTER_NAMES } from '../Filters';
import Results from '../Results';

import { Translation } from '../../api';

const RESULTS_PER_PAGE = 100;

export interface TranslationsReportProps {
    apiUrl: string;
}

const TranslationsReport: FunctionComponent<TranslationsReportProps> = ({apiUrl}) => {
    const queryStringParsed = parseQueryString(location.search);
    const initialFilters = new Map();
    for (let key in queryStringParsed) {
        if (FILTER_NAMES.indexOf(key) !== -1) {
            initialFilters.set(key, queryStringParsed[key]);
        }
    }

    const [filters, setFilters] = React.useState(initialFilters);
    const [filterErrors, setFilterErrors] = React.useState(null);
    const [serverError, setServerError] = React.useState(false);
    const [translations, setTranslations] = React.useState<Translation[]>([])
    const [isLoading, setIsLoading] = React.useState(false);

    console.log(filterErrors, serverError, isLoading);

    // These two need to be globally mutable and not trigger UI refreshes on update
    // If two requests are fired off at around the same time, this makes sure the later
    // always takes precedence over the earlier one
    const nextFetchId = React.useRef(1);
    const lastReceivedFetchId = React.useRef(0);

    const firstRun = React.useRef(true);

    // Actions that happen when filters change
    React.useEffect(() => {
        const queryParams: {[key: string]: string} = {};
        filters.forEach((value, key) => {
            queryParams[key] = value;
        });
        let queryString = stringifyQueryString(queryParams);

        // Update browser URL
        // Don't update it on initial page load so we don't strip any utm_* parameters
        if (!firstRun.current) {
            history.replaceState(
                {},
                document.title,
                document.location.pathname + (queryString ? `?${queryString}` : ''),
            );
        } else {
            firstRun.current = false;
        }

        // Fetch new results over API
        async function fetchData() {
            queryParams['page_size'] = RESULTS_PER_PAGE.toString();
            queryString = stringifyQueryString(queryParams);

            // Get a fetch ID
            // We do this so that if responses come back in a different order to
            // when the requests were sent, the older requests don't replace newer ones
            let thisFetchId = nextFetchId.current++;

            setIsLoading(true);

            const response = await fetch(
                apiUrl + (queryString ? `?${queryString}` : ''),
            );

            if (thisFetchId < lastReceivedFetchId.current) {
                // A subsequent fetch was made but its response came in before this one
                // So ignore this response
                return;
            }

            lastReceivedFetchId.current = thisFetchId;

            if (response.status === 200) {
                const json = await response.json();
                setTranslations(json);
                setFilterErrors(null);
            } else if (response.status === 400) {
                const json = await response.json();
                setFilterErrors(json);
            } else {
                console.error(
                    'Unrecognised status code returned',
                    response.status,
                );
                setServerError(true);
            }

            setIsLoading(false);
        }
        fetchData();
    }, [filters]);

    return (
        <>
            <Header
                title={gettext("Translations")}
                icon="site"
            />
            <div className="report report--has-filters">
                <div className="report__results">
                    <Results translations={translations} />
                </div>
                <div className="report__filters">
                    <h2>{gettext("Filter")}</h2>
                    <Filters filters={filters} setFilters={setFilters} />
                </div>
            </div>
        </>
    );
};

export default TranslationsReport;
