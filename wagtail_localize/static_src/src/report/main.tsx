import React from 'react';
import ReactDOM from 'react-dom';

import TranslationsReport from './components/TranslationsReport';

document.addEventListener('DOMContentLoaded', () => {
    const element = document.querySelector('.js-translations-report');

    if (element instanceof HTMLElement) {
        ReactDOM.render(<TranslationsReport apiUrl={element.dataset.apiUrl} />, element);
    }
});
