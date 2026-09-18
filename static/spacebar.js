'use strict';
window.StripshotSpace = {
  bind(root, trigger) {
    let held = false;
    root.addEventListener('keydown', event => {
      if (event.code !== 'Space') return;
      const editable = event.target?.closest?.('input, textarea, select, [contenteditable]');
      if (editable || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      if (held || event.repeat) return;
      held = true;
      trigger();
    });
    root.addEventListener('keyup', event => { if (event.code === 'Space') held = false; });
    window.addEventListener('blur', () => { held = false; });
  }
};
