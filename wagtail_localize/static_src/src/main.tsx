import React from 'react';
import ReactDOM from 'react-dom';

import TranslationEditor from './editor/components/TranslationEditor';

document.addEventListener('DOMContentLoaded', () => {
    const element = document.querySelector('.js-translation-editor');

    if (element instanceof HTMLElement) {
        ReactDOM.render(<TranslationEditor {...JSON.parse(element.dataset.props)} />, element);
    }
});
