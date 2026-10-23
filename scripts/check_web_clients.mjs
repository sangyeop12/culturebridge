/* Browser event contracts using the real client scripts with explicit test doubles.
 * This does not claim physical microphone, Android install or network integration QA.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const root = new URL('../src/culturebridge/web/', import.meta.url);
const source = name => fs.readFileSync(new URL(name, root), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function voice() {
  const emitted = [], field = {value: '', disabled: false}, handlers = {};
  let recognition;
  class Recognition {
    constructor() { recognition = this; }
    start() { this.onstart(); }
    abort() { throw new Error('already stopped'); }
  }
  const window = {isSecureContext: true, SpeechRecognition: Recognition,
    addEventListener: (name, callback) => {handlers[name] = callback;}};
  const document = {getElementById: () => ({matches: () => true, ...field}),
    addEventListener: (name, callback) => {handlers[name] = callback;}};
  vm.runInNewContext(source('voice.js'), {window, document,
    emitEvent: (_, data) => emitted.push(data), setTimeout: () => 1, clearTimeout: () => {}});
  const start = () => window.CultureBridgeVoice.start('target', 1);
  const result = text => {const r = [{transcript: text}]; r.isFinal = true;
    recognition.onresult({results: [r]});};
  start(); result('x'.repeat(1000));
  assert.equal(emitted.at(-1).code, 'result');
  start(); field.value = '수정한 입력'; result('덮어쓰면 안 됨');
  assert.equal(emitted.at(-1).code, 'edited');
  field.value = ''; start(); recognition.onerror({error: 'not-allowed'});
  assert.equal(emitted.at(-1).code, 'not-allowed');
  start(); result('다시 허용 후 입력');
  assert.equal(emitted.at(-1).code, 'result');
  start(); window.CultureBridgeVoice.cancel(); result('늦은 응답');
  assert.equal(emitted.at(-1).code, 'aborted');
  window.isSecureContext = false; start();
  assert.equal(emitted.at(-1).code, 'insecure');
  assert.equal(field.value, ''); // Never submits or writes recognition text directly.
}

async function pwa() {
  const handlers = {}, swHandlers = {}, elements = {}, posts = [], confirmations = [];
  let reloads = 0;
  const registration = {waiting: {postMessage: value => posts.push(value)}, addEventListener() {}};
  const window = {isSecureContext: true, confirm: () => true,
    addEventListener: (name, callback) => {handlers[name] = callback;}};
  const navigator = {onLine: true, serviceWorker: {
    addEventListener: (name, callback) => {swHandlers[name] = callback;},
    register: async () => registration,
  }};
  const document = {getElementById: id => (elements[id] ??= {textContent: ''})};
  vm.runInNewContext(source('pwa.js'), {window, navigator, document,
    emitEvent: name => confirmations.push(name),
    location: {reload: () => {reloads++;}}});
  await tick();
  handlers.beforeinstallprompt({preventDefault() {}, prompt: async () => {throw Error();}});
  await window.CultureBridgePWA.install();
  assert.match(elements['cb-install-status'].textContent, /열지 못했어요/);
  handlers.beforeinstallprompt({preventDefault() {}, prompt: async () => {},
    userChoice: Promise.resolve({outcome: 'dismissed'})});
  await window.CultureBridgePWA.install();
  assert.match(elements['cb-install-status'].textContent, /웹에서도/);
  window.CultureBridgePWA.update();
  assert.equal(posts.length, 0);
  assert.deepEqual(confirmations, ['cb_pwa_update_confirm']);
  window.CultureBridgePWA.applyUpdate();
  assert.equal(posts[0].type, 'SKIP_WAITING');
  swHandlers.controllerchange(); swHandlers.controllerchange();
  assert.equal(reloads, 1);
  navigator.onLine = false; handlers.offline();
  assert.match(elements['cb-connection-status'].textContent, /끊겼어요/);
  navigator.onLine = true; handlers.online();
  assert.match(elements['cb-connection-status'].textContent, /서버도/);
}

async function worker() {
  const handlers = {}, deleted = [], requests = [];
  const cache = {match: async key => key === '/pwa/offline' ? 'offline-page' : undefined,
    addAll: async urls => {assert.equal(urls.length, 4);}};
  const self = {location: {origin: 'http://localhost'}, clients: {claim: async () => {}},
    addEventListener: (name, callback) => {handlers[name] = callback;}};
  vm.runInNewContext(source('sw.js'), {self, URL,
    caches: {open: async () => cache, keys: async () => ['culturebridge-public-v1', 'unrelated'],
      delete: async key => {deleted.push(key);}},
    fetch: async request => {requests.push(request); throw Error('offline');}});
  let promise;
  handlers.activate({waitUntil: p => {promise = p;}}); await promise;
  assert.deepEqual(deleted, ['culturebridge-public-v1']);
  handlers.fetch({request: {method: 'GET', mode: 'navigate',
    url: 'http://localhost/learn?conversation_id=private'}, respondWith: p => {promise = p;}});
  assert.equal(await promise, 'offline-page');
  let intercepted = false;
  for (const request of [
    {method: 'POST', url: 'http://localhost/learn'},
    {method: 'GET', url: 'http://localhost/api/learning/conversations'},
    {method: 'GET', url: 'https://elsewhere.invalid/learn'},
  ]) handlers.fetch({request, respondWith: () => {intercepted = true;}});
  assert.equal(intercepted, false);
  assert.equal(requests.length, 1);
}

voice(); await pwa(); await worker();
console.log('Voice, installation/update and private-query offline contracts: passed (test doubles).');
