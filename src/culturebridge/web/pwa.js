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
      await event.prompt();
      const choice = await event.userChoice;
      status(choice.outcome === 'accepted' ? '홈 화면 추가를 요청했어요.' : '웹에서도 계속 이용할 수 있어요.');
    },
    update() {
      if (!registration?.waiting) return status('대기 중인 업데이트가 없어요.', 'cb-update-status');
      if (!window.confirm('작성 중인 입력은 사라질 수 있어요. 대화를 보낸 뒤 새 버전으로 바꿀까요?')) return;
      updateRequested = true;
      registration.waiting.postMessage({type: 'SKIP_WAITING'});
    },
  };
  if (!window.isSecureContext || !('serviceWorker' in navigator)) return;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (updateRequested) location.reload();
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
