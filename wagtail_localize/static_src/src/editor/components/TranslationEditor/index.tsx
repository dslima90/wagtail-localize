import React, { FunctionComponent } from 'react';
import gettext from 'gettext';

import Icon from '../../../common/components/Icon';
import ActionMenu from '../../../common/components/ActionMenu';
import Header, { HeaderLinkAction, HeaderMeta, HeaderMetaDropdown } from '../../../common/components/Header';

interface Object {
    title: string;
    liveUrl?: string;
}

interface Locale {
    code: string;
    displayName: string;
}

interface Translation {
    title: string;
    locale: Locale;
    editUrl?: string;
}

interface Permissions {
    canSaveDraft: boolean;
    canPublish: boolean;
    canUnpublish: boolean;
    canLock: boolean;
    canDelete: boolean;
}

interface StringSegment {
    id: number;
    contentPath: string;
    source: string;
    value: string;
}

interface TranslationEditorProps {
    object: Object;
    sourceLocale: Locale;
    locale: Locale;
    translations: Translation[];
    perms: Permissions;
    segments: StringSegment[];
}

const TranslationEditorHeader: FunctionComponent<TranslationEditorProps> = ({object, sourceLocale, locale, translations, segments}) => {
    // Build actions
    let actions = [];
    if (object.liveUrl) {
        actions.push(<HeaderLinkAction key="live" label={gettext("Live")} href={object.liveUrl} classes={["button-nostroke button--live"]} icon="link-external" />)
    }

    // Build meta
    let meta = [
        <HeaderMeta key="source-locale" value={sourceLocale.displayName}/>,
    ];

    let translationOptions = translations.filter(({locale}) => locale.code != sourceLocale.code).map(({locale, editUrl}) => {
        return {
            label: locale.displayName,
            href: editUrl,
        }
    });

    if (translationOptions.length > 0) {
        meta.push(<HeaderMetaDropdown
            label={locale.displayName}
            options={translationOptions}
        />);
    } else {
        meta.push(<HeaderMeta
            key="target-locale"
            value={locale.displayName}
        />);
    }

    let totalSegments = segments.length;
    let translatedSegments = segments.filter(({value}) => value).length;

    if (totalSegments == translatedSegments) {
        meta.push(<HeaderMeta key="progress" value={gettext("Up to date")}/>);
    } else {
        // TODO: Make translatable
        meta.push(<HeaderMeta key="progress" value={`In progress (${translatedSegments}/${totalSegments} strings)`}/>);
    }

    return (
        <Header
            title={object.title}
            actions={actions}
            meta={meta}
        />
    );
}

const TranslationEditorSegment: FunctionComponent<StringSegment> = (segment) => {
    return <div>
        <h3>{segment.contentPath}</h3>
        <p>{segment.source}</p>
        <textarea>{segment.value}</textarea>
    </div>
}

const TranslationEditorFooter: FunctionComponent<TranslationEditorProps> = ({perms}) => {
    let actions = [
        <a className="button action-secondary" href="/admin/pages/60/delete/">
            <Icon name="cross" />
            {gettext("Disable")}
        </a>
    ];

    if (perms.canDelete) {
        actions.push(
            <a className="button action-secondary" href="/admin/pages/60/delete/">
                <Icon name="bin" />
                {gettext("Delete")}
            </a>
        );
    }

    // TODO unlock
    if (perms.canLock) {
        actions.push(
            <button className="button action-secondary" data-locking-action="/admin/pages/60/lock/" aria-label={gettext("Apply editor lock")}>
                <Icon name="lock" />
                {gettext("Lock")}
            </button>
        );
    }

    if (perms.canUnpublish) {
        actions.push(
            <a className="button action-secondary" href="/admin/pages/60/unpublish/">
                <Icon name="download-alt" />
                {gettext("Unpublish")}
            </a>
        );
    }

    if (perms.canPublish) {
        actions.push(
            <button className="button button-longrunning " data-clicked-text={gettext("Publishing…")}>
                <Icon name="upload" className={"button-longrunning__icon"}  />
                <Icon name="spinner" />
                <em>{gettext("Publish")}</em>
            </button>
        );
    }

    if (perms.canSaveDraft) {
        actions.push(
            <button className="button action-save button-longrunning " data-clicked-text={gettext("Saving…")}>
                <Icon name="draft" className={"button-longrunning__icon"} />
                <Icon name="spinner" />
                <em>{gettext("Save draft")}</em>
            </button>
        );
    }

    // Make last action the default
    const defaultAction = actions.pop();

    return (
        <footer>
            <ActionMenu defaultAction={defaultAction} actions={actions} />
        </footer>
    );
}

const TranslationEditor: FunctionComponent<TranslationEditorProps> = (props) => {
    let segments = props.segments.map(segment => {
        return <TranslationEditorSegment key={segment.id} {...segment} />
    });

    return (
        <>
            <TranslationEditorHeader {...props} />
            <div className="nice-padding">{segments}</div>
            <TranslationEditorFooter {...props} />
        </>
    );
};

export default TranslationEditor;
