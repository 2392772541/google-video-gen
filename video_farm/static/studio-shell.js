/* Presentation-only navigation and accessibility. No task/API state is owned here. */
(() => {
  'use strict';
  document.addEventListener('DOMContentLoaded', () => {
    const buttons = [...document.querySelectorAll('button.tab-button[data-target]')];
    const title = document.getElementById('workspace-title');
    function syncNavigation() {
      for (const button of buttons) {
        const selected = button.classList.contains('active');
        if (selected) button.setAttribute('aria-current', 'page');
        else button.removeAttribute('aria-current');
        if (selected && title) title.textContent = button.querySelector('span:nth-child(2)')?.textContent || '工作空间';
      }
    }
    buttons.forEach(button => button.addEventListener('click', () => {
      syncNavigation();
      history.replaceState(null, '', '#' + button.dataset.target);
    }));
    function navigateHash() {
      const target = location.hash.slice(1);
      const button = buttons.find(item => item.dataset.target === target);
      if (button && !button.classList.contains('active')) button.click();
      syncNavigation();
    }
    const choices = [...document.querySelectorAll('.aspect-pill-btn,.duration-pill-btn,#btn-engine-flow,#btn-engine-gemini,#btn-mode-single,#btn-mode-batch')];
    const syncChoices = () => choices.forEach(button => button.setAttribute('aria-pressed', String(button.classList.contains('active'))));
    choices.forEach(button => button.addEventListener('click', () => queueMicrotask(syncChoices)));
    syncChoices();
    navigateHash();
    window.addEventListener('hashchange', navigateHash);
    document.querySelectorAll('.drop-card[tabindex],#accordion-toggle-adv').forEach(control => {
      control.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          control.click();
        }
      });
    });
    const advanced = document.getElementById('accordion-toggle-adv');
    const advancedBody = document.getElementById('accordion-body-adv');
    if (advanced && advancedBody) {
      advanced.setAttribute('aria-controls', advancedBody.id);
      const syncExpanded = () => advanced.setAttribute('aria-expanded', String(advancedBody.classList.contains('open') || advancedBody.classList.contains('show') || getComputedStyle(advancedBody).display !== 'none'));
      advanced.addEventListener('click', syncExpanded);
      syncExpanded();
    }
  });
})();
