// Browser API unit tests, not real microphone or device-installation verification.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const asset = name => fs.readFileSync(path.join(__dirname, '../src/culturebridge/web', name), 'utf8');

function voice({supported = true, secure = true} = {}) {
  const events = [], recognitions = [], timers = [], listeners = {};
  const field = {value: '', disabled: false};
  class Recognition {
    constructor() {recognitions.push(this);}
    start() {this.onstart();}
    abort() {this.aborted = true; this.onend?.();}
  }
  const context = {
    window: {isSecureContext: secure, addEventListener: (type, fn) => {listeners[type] = fn;}},
    document: {
      getElementById: () => ({matches: () => false, querySelector: () => field}),
      addEventListener: (type, fn) => {listeners[type] = fn;}, hidden: false,
    },
    emitEvent: (type, value) => events.push(value),
    setTimeout: fn => {timers.push(fn); return timers.length;}, clearTimeout: () => {},
  };
  if (supported) context.window.SpeechRecognition = Recognition;
  vm.runInNewContext(asset('voice.js'), context);
  const result = text => {
    const r = [{transcript: text}]; r.isFinal = true;
    recognitions.at(-1).onresult({results: [r]});
  };
  return {context, events, recognitions, timers, listeners, field, result, api: context.window.CultureBridgeVoice};
}

test('unsupported and insecure browsers keep text-only input', () => {
  for (const options of [{supported: false}, {secure: false}]) {
    const v = voice(options); v.field.value = '작성 중'; v.api.start('a', 1);
    assert.equal(v.recognitions.length, 0);
    assert.equal(v.field.value, '작성 중');
    assert.equal(v.events.at(-1).code, options.secure === false ? 'insecure' : 'unsupported');
  }
});
test('transcription emits text once, without submitting or editing the DOM', () => {
  const v = voice(); v.field.value = '기존'; v.api.start('a', 1); v.result('다보탑');
  assert.equal(v.events.at(-1).text, '다보탑');
  assert.equal(v.events.at(-1).base, '기존');
  assert.equal(v.field.value, '기존');
  assert.equal(v.events.filter(e => e.code === 'result').length, 1);
});
test('typing during recognition is never overwritten', () => {
  const v = voice(); v.api.start('a', 1); v.field.value = '직접 입력'; v.result('음성');
  assert.equal(v.events.at(-1).code, 'edited');
  assert.equal(v.field.value, '직접 입력');
});
test('permission failure, no speech, network errors do not automatically retry', () => {
  for (const error of ['not-allowed', 'service-not-allowed', 'network', 'audio-capture', 'no-speech']) {
    const v = voice(); v.api.start('a', 1); v.recognitions[0].onerror({error});
    assert.equal(v.events.at(-1).code, error);
    assert.equal(v.recognitions.length, 1);
  }
});
test('cancel, page hide and timeout discard late recognition results', () => {
  for (const stop of [v => v.api.cancel(), v => v.listeners.pagehide(), v => v.timers[0]()]) {
    const v = voice(); v.api.start('a', 1); stop(v); v.result('늦은 결과');
    assert.equal(v.events.filter(e => e.code === 'result').length, 0);
    assert.equal(v.recognitions[0].aborted, true);
  }
});
test('only one microphone session is active and oversized results are rejected', () => {
  const v = voice(); v.api.start('a', 1); v.api.start('b', 1);
  assert.equal(v.recognitions[0].aborted, true);
  v.result('x'.repeat(1001));
  assert.equal(v.events.at(-1).code, 'too-long');
});

function worker() {
  const handlers = {}, writes = [], deleted = [];
  let skips = 0;
  const context = {
    URL, fetch: async request => {writes.push(['fetch', request.url]); return 'network';},
    self: {
      location: {origin: 'https://example.test'}, clients: {claim: async () => {}},
      addEventListener: (type, fn) => {handlers[type] = fn;}, skipWaiting: () => {skips++;},
    },
    caches: {
      keys: async () => ['unrelated-cache', 'culturebridge-public-old', 'culturebridge-public-v1'],
      delete: async name => {deleted.push(name);},
      open: async () => ({
        addAll: async urls => {writes.push(['precache', ...urls]);},
        match: async request => `cached:${request.url || request}`,
      }),
    },
  };
  vm.runInNewContext(asset('sw.js'), context);
  const fetchEvent = (url, method = 'GET', mode = 'navigate') => {
    let response;
    handlers.fetch({request: {url, method, mode}, respondWith: promise => {response = promise;}});
    return response;
  };
  return {handlers, writes, deleted, context, fetchEvent, skips: () => skips};
}
test('service worker pre-caches only generic offline page and icons', async () => {
  const w = worker(); let done;
  w.handlers.install({waitUntil: promise => {done = promise;}}); await done;
  assert.deepEqual(w.writes[0], ['precache', '/pwa/offline', '/pwa/icon-180.png', '/pwa/icon-192.png', '/pwa/icon-512.png']);
});
test('API, external origins, query navigation and POST bypass service worker', () => {
  const w = worker();
  for (const url of ['https://example.test/api/learning/conversations', 'https://else.test/', 'https://example.test/learn?conversation_id=private']) {
    assert.equal(w.fetchEvent(url), undefined);
  }
  assert.equal(w.fetchEvent('https://example.test/learn', 'POST'), undefined);
});
test('personalised pages use network and are never written to cache', async () => {
  const w = worker();
  assert.equal(await w.fetchEvent('https://example.test/learn'), 'network');
  assert.deepEqual(w.writes, [['fetch', 'https://example.test/learn']]);
  w.context.fetch = async () => {throw new Error('offline');};
  assert.equal(await w.fetchEvent('https://example.test/learning-history'), 'cached:/pwa/offline');
});
test('activation deletes only owned old caches; updates do not skip waiting automatically', async () => {
  const w = worker(); let done;
  w.handlers.activate({waitUntil: promise => {done = promise;}}); await done;
  assert.deepEqual(w.deleted, ['culturebridge-public-old']);
  assert.equal(w.skips(), 0);
  w.handlers.message({data: {type: 'SKIP_WAITING'}});
  assert.equal(w.skips(), 1);
});

function client() {
  const listeners = {}, notices = {textContent: ''}, updateNotice = {textContent: ''}, sent = [];
  let reloads = 0, confirmed = false;
  const registration = {waiting: {postMessage: data => sent.push(data)}, addEventListener: () => {}};
  const context = {
    window: {isSecureContext: true, addEventListener: (name, fn) => {listeners[name] = fn;}, confirm: () => confirmed},
    document: {getElementById: id => id === 'cb-update-status' ? updateNotice : notices},
    navigator: {serviceWorker: {
      addEventListener: (name, fn) => {listeners[name] = fn;},
      register: async () => registration,
    }},
    location: {reload: () => {reloads++;}},
  };
  vm.runInNewContext(asset('pwa.js'), context);
  return {listeners, notices, sent, api: context.window.CultureBridgePWA,
    confirm: () => {confirmed = true;}, reloads: () => reloads};
}
test('installation without browser prompt provides manual guidance, not a false success', async () => {
  const c = client(); await c.api.install();
  assert.match(c.notices.textContent, /Safari/);
  assert.doesNotMatch(c.notices.textContent, /추가했어요/);
});
test('install prompt is invoked only after the install button action', async () => {
  const c = client(); let prompts = 0;
  c.listeners.beforeinstallprompt({preventDefault: () => {}, prompt: async () => {prompts++;}, userChoice: Promise.resolve({outcome: 'dismissed'})});
  assert.equal(prompts, 0);
  await c.api.install(); assert.equal(prompts, 1);
  assert.match(c.notices.textContent, /웹에서도/);
});
test('controller updates reload only after explicit confirmation', async () => {
  const c = client(); await Promise.resolve();
  c.listeners.controllerchange(); assert.equal(c.reloads(), 0);
  c.api.update(); assert.equal(c.sent.length, 0);
  c.confirm(); c.api.update(); assert.equal(c.sent[0].type, 'SKIP_WAITING');
  c.listeners.controllerchange(); assert.equal(c.reloads(), 1);
});
