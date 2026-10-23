/* Public assets only; installation and activating an update require user actions. */
(() => {
  let promptEvent = null;
  let registration = null;
  let updateRequested = false;
  const status = (text, id = 'cb-install-status') => {
    const element = document.getElementById(id);
    if (element) element.textContent = text;
  };
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    promptEvent = event;
    status('홈 화면에 추가할 수 있어요. 아래 버튼을 눌러주세요.');
  });
  window.addEventListener('appinstalled', () => {
    promptEvent = null;
    status('홈 화면에 추가했어요.');
  });
  window.CultureBridgePWA = {
    async install() {
      if (!promptEvent) {
        status('브라우저 메뉴의 앱 설치 또는 홈 화면에 추가를 이용해 주세요. iPhone은 Safari의 공유 메뉴에서 홈 화면에 추가를 선택해 주세요.');
        return;
      }
      const event = promptEvent;
      promptEvent = null;
      try {
        await event.prompt();
        const choice = await event.userChoice;
        status(choice.outcome === 'accepted' ? '홈 화면 추가를 요청했어요.' : '웹에서도 계속 이용할 수 있어요.');
      } catch {
        status('설치 창을 열지 못했어요. 브라우저 메뉴를 이용하거나 웹에서 계속 학습해 주세요.');
      }
    },
    update() {
      if (!registration?.waiting) return status('대기 중인 업데이트가 없어요.', 'cb-update-status');
      if (typeof emitEvent === 'function') emitEvent('cb_pwa_update_confirm');
      else status('확인 창을 열지 못했어요. 입력을 마친 뒤 다시 시도해 주세요.', 'cb-update-status');
    },
    applyUpdate() {
      if (!registration?.waiting) return status('대기 중인 업데이트가 없어요.', 'cb-update-status');
      updateRequested = true;
      try {
        registration.waiting.postMessage({type: 'SKIP_WAITING'});
      } catch {
        updateRequested = false;
        status('새 버전을 적용하지 못했어요. 작성한 내용을 보낸 뒤 다시 시도해 주세요.', 'cb-update-status');
      }
    },
  };
  const connection = () => status(navigator.onLine === false
    ? '브라우저 연결이 끊겼어요. 연결 전에는 질문을 보내지 마세요.'
    : '브라우저가 네트워크에 연결돼 있어요. 학습하려면 서버도 실행 중이어야 해요.', 'cb-connection-status');
  window.addEventListener('online', connection);
  window.addEventListener('offline', connection);
  window.addEventListener('DOMContentLoaded', connection);
  connection();
  if (!window.isSecureContext || !('serviceWorker' in navigator)) {
    status('이 환경에서는 홈 화면 추가를 준비할 수 없어요. 일반 웹으로 이용해 주세요.');
    return;
  }
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (updateRequested) { updateRequested = false; location.reload(); }
  });
  navigator.serviceWorker.register('/sw.js', {scope: '/', updateViaCache: 'none'})
    .then(value => {
      registration = value;
      const inform = () => {
        if (registration.waiting) status('새 버전이 준비됐어요. 입력을 마친 뒤 새 버전 적용을 눌러주세요.', 'cb-update-status');
      };
      inform();
      registration.addEventListener('updatefound', () => {
        registration.installing?.addEventListener('statechange', inform);
      });
    })
    .catch(() => status('홈 화면 추가 준비를 마치지 못했어요. 일반 웹 이용은 가능해요.'));
})();
