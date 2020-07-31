import React, { FunctionComponent } from 'react';
import gettext from 'gettext';

import { Translation } from '../../api';

interface TitleProps {
    title: string;
    editUrl: string;
    contentType: string;
}

const Title: FunctionComponent<TitleProps> = ({title, editUrl, contentType}) => {
    if (editUrl) {
        return <a href={editUrl}>{title} - {contentType}</a>;
    } else {
        return <>{title} - {contentType}</>;
    }
};

interface ResultsProps {
    translations: Translation[];
}

const Results: FunctionComponent<ResultsProps> = ({translations}) => {
    return (
        <table className="listing">
            <thead>
                <th>{gettext("Translation of")}</th>
                <th>{gettext("To")}</th>
                <th>{gettext("Progress")}</th>
            </thead>
            <tbody>
                {translations.map(translation => {
                    return (
                        <tr>
                            <td><Title title={translation.source.object_repr} editUrl={translation.edit_url} contentType={translation.source.content_type} /></td>
                            <td>{translation.target_locale.display_name || translation.target_locale.language_code}</td>
                            <td>{translation.translated_strings} / {translation.total_strings} strings translated</td>
                        </tr>
                    )
                })}
            </tbody>
        </table>
    )
};

export default Results;
