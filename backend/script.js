(() => {
  'use strict';

  const display = document.getElementById('display');

  let justEvaluated = false;

  function getDisplay() {
    return display.textContent.replace(/\s+/g, '');
  }

  function setDisplay(val) {
    display.textContent = val;
  }

  function sanitize(expr) {
    // Keep digits, operators, parentheses, and dot. Remove whitespace.
    return expr.replace(/[^0-9+\-*/.()]/g, '');
  }

  function safeEval(expr) {
    const sanitized = sanitize(expr);
    if (!sanitized) return null;
    // Disallow consecutive operators
    if (/[+\-*/]{2,}/.test(sanitized)) return null;
    // Block obviously malicious tokens just in case (defense in depth)
    if (/[a-df-zA-DF-Z]/.test(sanitized)) return null;
    try {
      // Evaluate with Function for controlled scope
      const result = Function('"use strict"; return (' + sanitized + ')')();
      if (typeof result !== 'number' || !isFinite(result)) return null;
      return result;
    } catch {
      return null;
    }
  }

  function appendCharacter(ch) {
    if (justEvaluated) {
      setDisplay(ch);
      justEvaluated = false;
      return;
    }
    const current = getDisplay();
    if (current === '0' && /[0-9.]/.test(ch)) {
      setDisplay(ch);
      return;
    }
    if (/[+\-*/]/.test(ch)) {
      if (/[+\-*/]$/.test(current)) {
        // Replace last operator
        setDisplay(current.replace(/[+\-*/]+$/, ch));
      } else {
        setDisplay(current + ch);
      }
    } else {
      setDisplay(current + ch);
    }
  }

  function clearAll() {
    setDisplay('0');
    justEvaluated = false;
  }

  function deleteLast() {
    if (justEvaluated) {
      clearAll();
      return;
    }
    const current = getDisplay();
    if (current.length <= 1) {
      setDisplay('0');
      return;
    }
    setDisplay(current.slice(0, -1) || '0');
  }

  function equals() {
    const current = getDisplay();
    if (/[+\-*/.]$/.test(current)) {
      // Don't evaluate with trailing operator
      return;
    }
    const result = safeEval(current);
    if (result === null) {
      setDisplay('Error');
    } else {
      setDisplay(String(result));
    }
    justEvaluated = true;
  }

  // Button clicks
  document.querySelectorAll('.btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const { value, action } = btn.dataset;
      if (value !== undefined) {
        appendCharacter(value);
      } else if (action) {
        if (action === 'clear') clearAll();
        else if (action === 'delete') deleteLast();
        else if (action === 'equals') equals();
      }
    });
  });

  // Keyboard support
  window.addEventListener('keydown', (e) => {
    const key = e.key;

    if (/[0-9]/.test(key)) {
      appendCharacter(key);
      e.preventDefault();
      return;
    }

    if (key === '.' || key === '+' || key === '-' || key === '*' || key === '/') {
      appendCharacter(key);
      e.preventDefault();
      return;
    }

    if (key === 'Enter' || key === '=') {
      equals();
      e.preventDefault();
      return;
    }

    if (key === 'Backspace') {
      deleteLast();
      e.preventDefault();
      return;
    }

    if (key === 'Escape' || key.toLowerCase() === 'c') {
      clearAll();
      e.preventDefault();
      return;
    }

    // Prevent accidental form submits etc.
    if (['(', ')', '%'].includes(key)) {
      e.preventDefault();
    }
  });
})();