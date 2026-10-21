/* Optional browser recognition. No recording, automatic sending, or server audio upload. */
(() => {
  let active = null;
  const notify = (target, code, extra = {}) => {
    if (typeof emitEvent === 'function') emitEvent('cb_voice', {target, code, ...extra});
  };
  const input = id => {
    const root = document.getElementById(`c${id}`);
    return root?.matches('textarea') ? root : root?.querySelector('textarea');
  };
  const cancel = () => {
    if (!active) return;
    const session = active;
    active = null;
    clearTimeout(session.timer);
    session.recognition.abort();
    notify(session.target, 'aborted');
  };
  window.CultureBridgeVoice = {
    cancel,
    start(target, inputId) {
      cancel();
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!window.isSecureContext) return notify(target, 'insecure');
      if (!Recognition) return notify(target, 'unsupported');
      const field = input(inputId);
      if (!field || field.disabled) return;
      try {
        const recognition = new Recognition();
        const session = {recognition, target, base: field.value, timer: null};
        active = session;
        recognition.lang = 'ko-KR';
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.onstart = () => {
          if (active === session) notify(target, 'listening');
        };
        recognition.onresult = event => {
          if (active !== session) return;
          const text = Array.from(event.results).filter(r => r.isFinal)
            .map(r => r[0].transcript).join(' ').trim();
          const current = input(inputId);
          if (!current || current.disabled || current.value !== session.base) {
            notify(target, 'edited');
          } else if (!text || text.length + session.base.length + 1 > 1000) {
            notify(target, 'too-long');
          } else {
            notify(target, 'result', {text, base: session.base});
          }
          active = null;
          clearTimeout(session.timer);
          recognition.abort();
        };
        recognition.onerror = event => {
          if (active !== session) return;
          active = null;
          clearTimeout(session.timer);
          const code = ['not-allowed', 'service-not-allowed', 'audio-capture', 'no-speech',
            'network', 'aborted'].includes(event.error) ? event.error : 'failed';
          notify(target, code);
        };
        recognition.onend = () => {
          if (active !== session) return;
          active = null;
          clearTimeout(session.timer);
          notify(target, 'no-speech');
        };
        recognition.start();
        session.timer = setTimeout(() => {
          if (active === session) cancel();
        }, 30000);
      } catch {
        cancel();
        notify(target, 'failed');
      }
    },
  };
  window.addEventListener('pagehide', cancel);
  document.addEventListener('visibilitychange', () => {if (document.hidden) cancel();});
})();
