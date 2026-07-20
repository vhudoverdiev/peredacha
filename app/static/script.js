try {
  const preparedNavigationUrl = new URL(window.location.href);
  if (preparedNavigationUrl.searchParams.has('_crm_prepared_navigation')) {
    preparedNavigationUrl.searchParams.delete('_crm_prepared_navigation');
    window.history.replaceState(
      window.history.state,
      '',
      `${preparedNavigationUrl.pathname}${preparedNavigationUrl.search}${preparedNavigationUrl.hash}`,
    );
  }
} catch (error) {}

const desktopPointerQueries = ['(hover: hover)', '(any-hover: hover)', '(pointer: fine)', '(any-pointer: fine)'];
const getNavigatorInfo = () => window.navigator || {};
const DESKTOP_REFERENCE_WIDTH = 1920;
const DESKTOP_REFERENCE_HEIGHT = 1080;
const DESKTOP_TO_MOBILE_VIEWPORT_WIDTH = 768;
const isIpadOsLike = () => {
  const nav = getNavigatorInfo();
  return nav.platform === 'MacIntel' && (nav.maxTouchPoints || 0) > 1;
};
const isRealPhoneDevice = () => {
  const nav = getNavigatorInfo();
  const userAgent = nav.userAgent || '';
  return nav.userAgentData?.mobile === true
    || /iPhone|iPod|Windows Phone|webOS|BlackBerry|Opera Mini|IEMobile/i.test(userAgent)
    || (/Android/i.test(userAgent) && /Mobile/i.test(userAgent));
};
const isTabletTouchDevice = () => {
  const nav = getNavigatorInfo();
  const userAgent = nav.userAgent || '';
  const maxTouchPoints = nav.maxTouchPoints || 0;
  return hasCoarseTouchPointer()
    && !isRealPhoneDevice()
    && (
      isIpadOsLike()
    || /iPad|Tablet|PlayBook|Silk|Kindle|KFAPWI|SM-T|Lenovo Tab/i.test(userAgent)
    || (/Android/i.test(userAgent) && !/Mobile/i.test(userAgent) && maxTouchPoints > 0)
    );
};
const hasCoarseTouchPointer = () => window.matchMedia('(hover: none) and (pointer: coarse)').matches;
const isPhoneTouchDevice = () => isRealPhoneDevice() && hasCoarseTouchPointer();
const isTouchAppDevice = () => isPhoneTouchDevice() || isTabletTouchDevice();
const getViewportWidth = () => Math.max(
  320,
  Math.round(window.visualViewport?.width || window.innerWidth || document.documentElement.clientWidth || DESKTOP_REFERENCE_WIDTH),
);
const getViewportHeight = () => Math.max(
  480,
  Math.round(window.visualViewport?.height || window.innerHeight || document.documentElement.clientHeight || DESKTOP_REFERENCE_HEIGHT),
);
const mobileEntrySkipStorageKey = 'crm-mobile-nav-skip-entry';
const hideStandaloneBootSplash = (immediate = false) => {
  if (typeof window.crmHideStandaloneBootSplash === 'function') {
    window.crmHideStandaloneBootSplash(immediate);
    return;
  }
  if (!document.documentElement.classList.contains('mobile-standalone-boot')) return;
  document.documentElement.classList.add('mobile-standalone-boot-hidden');
};

// Keep fixed mobile navigation attached to the root viewport. Ancestors of
// the page content are animated/resized and can otherwise become a containing
// block for position: fixed on iOS standalone launches.
const mobileRootNavigation = document.querySelector('.mobile-bottom-nav');
if (mobileRootNavigation && isTouchAppDevice() && mobileRootNavigation.parentElement !== document.body) {
  document.body.appendChild(mobileRootNavigation);
  mobileRootNavigation.classList.add('mobile-bottom-nav-root');
}

const getDesktopReferenceWidth = () => DESKTOP_REFERENCE_WIDTH;
const getDesktopStageScale = () => Math.min(1, getViewportWidth() / DESKTOP_REFERENCE_WIDTH);
const shouldAllowAdaptiveMobileViewport = () => false;
const isAdaptiveMobileViewport = () => shouldAllowAdaptiveMobileViewport() && !isTouchAppDevice() && getViewportWidth() <= DESKTOP_TO_MOBILE_VIEWPORT_WIDTH;
const isTouchMobileViewport = () => isPhoneTouchDevice() || isTabletTouchDevice();
const isMobileViewport = () => isTouchMobileViewport() || isAdaptiveMobileViewport();
const isDesktopLikePointer = () => !isTouchAppDevice() && !isAdaptiveMobileViewport();
const shouldUseDesktopViewportLock = () => isDesktopLikePointer();
const rememberInstantMobileEntryForNextNavigation = href => {
  if (!document.body?.classList.contains('app-body')) return;
  if (!isMobileViewport()) return;
  try {
    const targetUrl = new URL(href || window.location.href, window.location.href);
    const currentUrl = new URL(window.location.href);
    if (targetUrl.origin !== currentUrl.origin) return;
    if (`${targetUrl.pathname}${targetUrl.search}${targetUrl.hash}` === `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`) return;
    window.sessionStorage.setItem(mobileEntrySkipStorageKey, '1');
  } catch (error) {}
};

// Every in-app link marks the next document as an internal transition. This
// keeps the native/HTML launch cover exclusive to a real app start or reload;
// ordinary navigation therefore cannot repaint the fixed header or dock.
document.addEventListener('click', event => {
  const link = event.target.closest?.('a[href]');
  if (!link || link.hasAttribute('download')) return;
  if (link.target && link.target !== '_self') return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  rememberInstantMobileEntryForNextNavigation(link.href);
}, true);

// Firefox paints its default white document for one frame while replacing
// two server-rendered pages. On desktop, fully receive the next HTML response
// first and hand it to the service worker as a one-use navigation response.
// The old document therefore stays visible until the destination is ready,
// while the real page navigation (and all page scripts) still runs normally.
const desktopFirefoxNavigationCache = 'crm-desktop-navigation-v1';
let desktopFirefoxNavigationInFlight = false;

const requestDesktopNavigationWorkerCapability = () => new Promise(resolve => {
  const controller = navigator.serviceWorker?.controller;
  if (!controller || typeof MessageChannel !== 'function') {
    resolve(false);
    return;
  }

  const channel = new MessageChannel();
  const timeout = window.setTimeout(() => resolve(false), 300);
  channel.port1.onmessage = event => {
    window.clearTimeout(timeout);
    resolve(event.data?.type === 'crm-desktop-navigation-capability-ready');
  };
  controller.postMessage(
    { type: 'crm-desktop-navigation-capability' },
    [channel.port2],
  );
});

let desktopNavigationWorkerCapability = requestDesktopNavigationWorkerCapability();
navigator.serviceWorker?.addEventListener('controllerchange', () => {
  desktopNavigationWorkerCapability = requestDesktopNavigationWorkerCapability();
});

const isDesktopFirefoxPreparedNavigation = () => (
  document.body?.classList.contains('app-body')
  && isDesktopLikePointer()
  && /Firefox\//i.test(getNavigatorInfo().userAgent || '')
  && 'caches' in window
  && Boolean(navigator.serviceWorker?.controller)
);

const getPreparedDesktopNavigationUrl = (event, link) => {
  if (!link || event.defaultPrevented || event.button !== 0) return null;
  if (link.hasAttribute('download') || link.dataset.downloadMode) return null;
  if (link.target && link.target !== '_self') return null;
  if (link.hasAttribute('data-bs-toggle')) return null;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return null;

  try {
    const targetUrl = new URL(link.href, window.location.href);
    const currentUrl = new URL(window.location.href);
    if (targetUrl.origin !== currentUrl.origin || !/^https?:$/.test(targetUrl.protocol)) return null;
    if (
      targetUrl.pathname === currentUrl.pathname
      && targetUrl.search === currentUrl.search
      && targetUrl.hash
    ) return null;
    return targetUrl;
  } catch (error) {
    return null;
  }
};

document.addEventListener('click', async event => {
  if (!isDesktopFirefoxPreparedNavigation()) return;
  const link = event.target.closest?.('a[href]');
  const targetUrl = getPreparedDesktopNavigationUrl(event, link);
  if (!targetUrl) return;

  event.preventDefault();
  if (desktopFirefoxNavigationInFlight) return;
  desktopFirefoxNavigationInFlight = true;

  let navigationUrl = targetUrl;
  try {
    if (!await desktopNavigationWorkerCapability) {
      throw new Error('prepared-navigation-worker-is-not-ready');
    }
    const response = await fetch(targetUrl.href, {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      redirect: 'follow',
      headers: {
        Accept: 'text/html,application/xhtml+xml',
        'X-CRM-Prepared-Navigation': '1',
      },
    });
    const contentType = response.headers.get('Content-Type') || '';
    if (!response.ok || !contentType.toLowerCase().includes('text/html')) {
      throw new Error('prepared-navigation-response-is-not-html');
    }

    navigationUrl = new URL(response.url || targetUrl.href, window.location.href);
    if (navigationUrl.origin !== window.location.origin) {
      throw new Error('prepared-navigation-cross-origin-redirect');
    }

    const cache = await window.caches.open(desktopFirefoxNavigationCache);
    navigationUrl.searchParams.set(
      '_crm_prepared_navigation',
      `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`,
    );
    const cacheKey = new Request(navigationUrl.href, {
      method: 'GET',
      credentials: 'same-origin',
    });
    await cache.put(cacheKey, response);
  } catch (error) {
    // Navigation must remain functional when the worker/cache is unavailable.
  }

  window.location.assign(navigationUrl.href);
}, true);

const getTouchViewportProfile = () => {
  const viewportWidth = getViewportWidth();
  const viewportHeight = getViewportHeight();
  const shortEdge = Math.min(viewportWidth, viewportHeight);
  const longEdge = Math.max(viewportWidth, viewportHeight);
  if (isTabletTouchDevice()) {
    return viewportHeight >= viewportWidth ? 'tablet-portrait' : 'tablet-landscape';
  }
  if (shortEdge <= 390 || longEdge <= 760) return 'phone-compact';
  if (shortEdge >= 430 || longEdge >= 920) return 'phone-large';
  return 'phone-standard';
};
const applyTouchViewportProfile = () => {
  const profileClassNames = [
    'touch-profile-phone-compact',
    'touch-profile-phone-standard',
    'touch-profile-phone-large',
    'touch-profile-tablet-portrait',
    'touch-profile-tablet-landscape',
  ];
  document.documentElement.classList.remove(...profileClassNames);
  document.body?.classList.remove(...profileClassNames);
  if (!isTouchAppDevice()) {
    document.documentElement.style.removeProperty('--crm-touch-shell-max-width');
    document.documentElement.style.removeProperty('--crm-touch-shell-gutter');
    document.documentElement.style.removeProperty('--crm-touch-shell-radius');
    return;
  }
  const profile = getTouchViewportProfile();
  const profileConfig = ({
    'phone-compact': { className: 'touch-profile-phone-compact', maxWidth: '25.75rem', gutter: '.82rem', radius: '1.42rem' },
    'phone-standard': { className: 'touch-profile-phone-standard', maxWidth: '27rem', gutter: '.94rem', radius: '1.5rem' },
    'phone-large': { className: 'touch-profile-phone-large', maxWidth: '28.5rem', gutter: '1.02rem', radius: '1.58rem' },
    'tablet-portrait': { className: 'touch-profile-tablet-portrait', maxWidth: '29.75rem', gutter: '1.08rem', radius: '1.64rem' },
    'tablet-landscape': { className: 'touch-profile-tablet-landscape', maxWidth: '31rem', gutter: '1.14rem', radius: '1.7rem' },
  })[profile];
  document.documentElement.classList.add(profileConfig.className);
  document.body?.classList.add(profileConfig.className);
  document.documentElement.style.setProperty('--crm-touch-shell-max-width', profileConfig.maxWidth);
  document.documentElement.style.setProperty('--crm-touch-shell-gutter', profileConfig.gutter);
  document.documentElement.style.setProperty('--crm-touch-shell-radius', profileConfig.radius);
};
const normalizeConfirmText = (text) => (text || '').replace(/\\n/g, '\n').replace(/\\t/g, '\t');
let desktopViewportSyncUnlocked = document.readyState === 'complete';
let lastCustomSelectViewportMode = null;

try {
  if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual';
} catch (error) {}

const syncDesktopViewportLock = (options = {}) => {
  const force = options === true || (typeof options === 'object' && options?.force === true);
  if (!force && !desktopViewportSyncUnlocked) return;
  const desktopLike = shouldUseDesktopViewportLock();
  const adaptiveMobileViewport = isAdaptiveMobileViewport();
  const phoneTouchDevice = isPhoneTouchDevice();
  const tabletTouchDevice = isTabletTouchDevice();
  const touchAppDevice = isTouchAppDevice();
  document.documentElement.classList.toggle('desktop-like-pointer', desktopLike);
  document.body?.classList.toggle('desktop-like-pointer', desktopLike);
  document.documentElement.classList.toggle('adaptive-mobile-viewport', adaptiveMobileViewport);
  document.body?.classList.toggle('adaptive-mobile-viewport', adaptiveMobileViewport);
  document.documentElement.classList.toggle('touch-app-device', touchAppDevice);
  document.body?.classList.toggle('touch-app-device', touchAppDevice);
  document.documentElement.classList.toggle('real-phone-device', phoneTouchDevice);
  document.body?.classList.toggle('real-phone-device', phoneTouchDevice);
  document.documentElement.classList.toggle('tablet-touch-device', tabletTouchDevice);
  document.body?.classList.toggle('tablet-touch-device', tabletTouchDevice);
  applyTouchViewportProfile();
  if (!desktopLike) {
    document.documentElement.style.removeProperty('--desktop-lock-width');
    document.documentElement.style.removeProperty('--desktop-reference-width');
    document.documentElement.style.removeProperty('--desktop-reference-height');
    document.documentElement.style.removeProperty('--desktop-stage-scale');
    return;
  }
  const desktopReferenceWidth = getDesktopReferenceWidth();
  const desktopStageScale = getDesktopStageScale();
  document.documentElement.style.setProperty('--desktop-reference-width', `${desktopReferenceWidth}px`);
  document.documentElement.style.setProperty('--desktop-reference-height', `${DESKTOP_REFERENCE_HEIGHT}px`);
  document.documentElement.style.setProperty('--desktop-lock-width', `${desktopReferenceWidth}px`);
  document.documentElement.style.setProperty('--desktop-stage-scale', desktopStageScale.toFixed(4));
};

(() => {
  syncDesktopViewportLock({ force: true });
  const startedAt = Date.now();
  const standaloneBootMinVisibleMs = document.documentElement.classList.contains('mobile-standalone-boot') ? 1600 : 0;
  const mobileDevLoaders = document.querySelectorAll('.mobile-dev-screen.site-page-loader');
  const scheduleStandaloneBootSplashHide = (delay = 90) => {
    if (!document.documentElement.classList.contains('mobile-standalone-boot')) return;
    const elapsed = Date.now() - startedAt;
    const minDelay = Math.max(0, standaloneBootMinVisibleMs - elapsed);
    window.setTimeout(() => hideStandaloneBootSplash(), Math.max(delay, minDelay));
  };
  const suppressStaticCrmLoaders = (forceDisplayNone = false) => {
    document.documentElement.classList.add('crm-loader-suppressed');
    hideStandaloneBootSplash(forceDisplayNone);
    document.querySelectorAll('.js-success-loader, .js-app-launch-loader, .mobile-dev-screen.site-page-loader').forEach(loader => {
      loader.classList.add('is-hidden');
      loader.style.pointerEvents = 'none';
      if (forceDisplayNone) loader.style.display = 'none';
    });
  };
  if (document.documentElement.classList.contains('crm-loader-suppressed')) {
    suppressStaticCrmLoaders(true);
  }
  if (!isTouchAppDevice()) {
    document.querySelectorAll('.viewport-transition-loader, .mobile-dev-screen.site-page-loader').forEach(loader => {
      loader.classList.add('is-hidden');
      loader.style.display = 'none';
      loader.style.pointerEvents = 'none';
    });
  }
  const loaders = document.querySelectorAll('.js-success-loader, .js-app-launch-loader');
  const hasAuthIntroLoader = Boolean(document.body?.classList.contains('auth-body') && document.querySelector('.js-app-launch-loader'));
  const hideMobileDevLoaders = (forceDisplayNone = false) => {
    mobileDevLoaders.forEach(loader => {
      loader.classList.add('is-hidden');
      loader.style.pointerEvents = 'none';
      if (forceDisplayNone) loader.style.display = 'none';
    });
  };
  const hideMobileDevLoadersWithDelay = () => {
    const delay = document.readyState === 'complete' ? 220 : 320;
    window.setTimeout(() => hideMobileDevLoaders(true), delay);
  };
  if (!loaders.length) {
    if (mobileDevLoaders.length) {
      if (document.readyState === 'complete') {
        hideMobileDevLoadersWithDelay();
      } else {
        window.addEventListener('load', hideMobileDevLoadersWithDelay, { once: true });
      }
      window.addEventListener('beforeunload', () => hideMobileDevLoaders(true));
      window.addEventListener('pagehide', () => hideMobileDevLoaders(true));
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') hideMobileDevLoaders(true);
      });
    }
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => scheduleStandaloneBootSplashHide(70));
    });
    return;
  }
  const minVisibleMs = hasAuthIntroLoader
    ? 2400
    : standaloneBootMinVisibleMs;
  const hide = () => {
    const delay = Math.max(0, minVisibleMs - (Date.now() - startedAt));
    window.setTimeout(() => {
      loaders.forEach(loader => loader.classList.add('is-hidden'));
      hideMobileDevLoaders(true);
    }, delay);
  };
  if (document.readyState === 'complete') {
    scheduleStandaloneBootSplashHide();
  } else {
    window.addEventListener('load', () => scheduleStandaloneBootSplashHide(), { once: true });
  }
  if (document.readyState === 'complete') {
    hide();
  } else {
    window.addEventListener('load', hide, { once: true });
  }
  window.addEventListener('beforeunload', () => suppressStaticCrmLoaders(true));
  window.addEventListener('pagehide', () => suppressStaticCrmLoaders(true));
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') suppressStaticCrmLoaders(true);
  });
  if (mobileDevLoaders.length) {
    if (document.readyState === 'complete') {
      hideMobileDevLoadersWithDelay();
    } else {
      window.addEventListener('load', hideMobileDevLoadersWithDelay, { once: true });
    }
  }
})();

window.addEventListener('load', () => {
  desktopViewportSyncUnlocked = true;
  syncDesktopViewportLock({ force: true });
}, { once: true });

// iOS standalone can restore the login document while creating a new cookie
// session. Refresh the CSRF value immediately before the first submit so the
// token and the active session always belong together.
document.addEventListener('submit', async event => {
  const form = event.target.closest?.('.js-login-fresh-csrf');
  if (!form || form.dataset.csrfReady === '1') return;

  event.preventDefault();
  event.stopImmediatePropagation();
  const submitter = event.submitter || form.querySelector('[type="submit"]');
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }

  if (submitter) submitter.disabled = true;
  try {
    const response = await fetch(form.dataset.csrfRefreshUrl || '/csrf-token', {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.csrf_token) throw new Error('csrf-refresh-failed');
    const field = form.querySelector('input[name="csrf_token"]');
    if (!field) throw new Error('csrf-field-missing');
    field.value = data.csrf_token;
    form.dataset.csrfReady = '1';
    if (submitter) submitter.disabled = false;
    form.requestSubmit(submitter || undefined);
  } catch (error) {
    if (submitter) submitter.disabled = false;
    window.location.replace(form.action || '/login');
  }
}, true);

document.addEventListener('DOMContentLoaded', () => {
  const mobileProjectToggle = document.querySelector('[data-mobile-project-toggle]');
  const mobileProjectPanel = document.querySelector('[data-mobile-project-panel]');
  if (mobileProjectToggle && mobileProjectPanel) {
    const mobileProjectPanelViewportGap = 10;
    const mobileProjectPanelMaxWidth = 440;
    const mobileProjectPanelSideInset = () => {
      const cssInset = parseFloat(
        window.getComputedStyle(document.documentElement).getPropertyValue('--crm-touch-shell-gutter')
      );
      return Number.isFinite(cssInset) && cssInset > 0 ? cssInset * 16 : 12;
    };
    const positionMobileProjectPanel = () => {
      if (mobileProjectPanel.hidden) return;
      const toggleRect = mobileProjectToggle.getBoundingClientRect();
      const sideInset = mobileProjectPanelSideInset();
      const availableWidth = Math.max(260, window.innerWidth - sideInset * 2);
      mobileProjectPanel.style.setProperty('top', `${Math.round(toggleRect.bottom + mobileProjectPanelViewportGap)}px`, 'important');
      mobileProjectPanel.style.setProperty('left', `${Math.round(window.innerWidth / 2)}px`, 'important');
      mobileProjectPanel.style.setProperty('width', `${Math.min(availableWidth, mobileProjectPanelMaxWidth)}px`, 'important');
      mobileProjectPanel.style.setProperty('max-width', `${Math.min(availableWidth, mobileProjectPanelMaxWidth)}px`, 'important');
    };
    if (mobileProjectPanel.parentElement !== document.body) {
      document.body.appendChild(mobileProjectPanel);
    }
    const closeMobileProjectPanel = () => {
      mobileProjectToggle.setAttribute('aria-expanded', 'false');
      mobileProjectToggle.classList.remove('is-open');
      mobileProjectPanel.classList.remove('is-open');
      document.body.classList.remove('mobile-project-switch-open');
      window.setTimeout(() => {
        if (!mobileProjectPanel.classList.contains('is-open')) {
          mobileProjectPanel.hidden = true;
          mobileProjectPanel.style.removeProperty('top');
          mobileProjectPanel.style.removeProperty('left');
          mobileProjectPanel.style.removeProperty('width');
          mobileProjectPanel.style.removeProperty('max-width');
        }
      }, 180);
    };
    const openMobileProjectPanel = () => {
      mobileProjectPanel.hidden = false;
      positionMobileProjectPanel();
      window.requestAnimationFrame(() => {
        positionMobileProjectPanel();
        mobileProjectToggle.setAttribute('aria-expanded', 'true');
        mobileProjectToggle.classList.add('is-open');
        mobileProjectPanel.classList.add('is-open');
        document.body.classList.add('mobile-project-switch-open');
      });
    };
    mobileProjectToggle.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      if (mobileProjectPanel.classList.contains('is-open')) closeMobileProjectPanel();
      else openMobileProjectPanel();
    });
    document.addEventListener('click', event => {
      if (!mobileProjectPanel.classList.contains('is-open')) return;
      if (mobileProjectPanel.contains(event.target) || mobileProjectToggle.contains(event.target)) return;
      closeMobileProjectPanel();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && mobileProjectPanel.classList.contains('is-open')) {
        closeMobileProjectPanel();
        mobileProjectToggle.focus({ preventScroll: true });
      }
    });
    window.addEventListener('resize', () => {
      if (mobileProjectPanel.classList.contains('is-open')) positionMobileProjectPanel();
    });
    window.addEventListener('scroll', () => {
      if (mobileProjectPanel.classList.contains('is-open')) positionMobileProjectPanel();
    }, { passive: true });
  }

  document.querySelectorAll('.crm-search-btn').forEach(button => {
    const lockButtonSize = () => {
      const rect = button.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      button.style.width = `${Math.ceil(rect.width)}px`;
      button.style.minWidth = `${Math.ceil(rect.width)}px`;
      button.style.height = `${Math.ceil(rect.height)}px`;
      button.style.minHeight = `${Math.ceil(rect.height)}px`;
    };
    button.addEventListener('pointerdown', lockButtonSize, { passive: true });
    button.addEventListener('touchstart', lockButtonSize, { passive: true });
  });

  let activeInlineEditor = null;

  const isIosDevice = /iPad|iPhone|iPod/.test(window.navigator.userAgent || '') || isIpadOsLike();
  const isStandaloneApp = window.navigator.standalone === true
    || window.matchMedia('(display-mode: standalone)').matches;
  const isCoarsePointer = window.matchMedia('(pointer: coarse)').matches;
  const mobileViewportMedia = window.matchMedia('(max-width: 767.98px)');
  const shouldUseStableStandaloneAppHeight = () => Boolean(
    document.body?.classList.contains('app-body')
    && isIosDevice
    && isStandaloneApp
    && isMobileViewport()
  );
  const getStableAppViewportHeight = () => {
    const layoutViewportHeight = Math.round(window.innerHeight || document.documentElement.clientHeight || 0);
    const visualViewportHeight = Math.round(window.visualViewport?.height || 0);
    if (shouldUseStableStandaloneAppHeight()) {
      return layoutViewportHeight || visualViewportHeight;
    }
    return Math.round(window.visualViewport?.height || window.innerHeight || document.documentElement.clientHeight || 0);
  };

  const syncAppViewportHeight = () => {
    if (!isIosDevice && !isMobileViewport()) return;
    const height = getStableAppViewportHeight();
    if (height > 0) document.documentElement.style.setProperty('--app-height', `${height}px`);
  };

  const syncMobileViewportClass = () => {
    const mobileViewport = isMobileViewport();
    document.documentElement.classList.toggle('mobile-viewport', mobileViewport);
    document.body.classList.toggle('mobile-viewport', mobileViewport);
  };

  const syncMobileOrientationLockState = () => {
    const landscapeLocked = isTouchAppDevice() && window.matchMedia('(orientation: landscape)').matches;
    document.documentElement.classList.toggle('mobile-landscape-locked', landscapeLocked);
    document.body.classList.toggle('mobile-landscape-locked', landscapeLocked);
  };

  const syncStandaloneBottomChrome = () => {
    const root = document.documentElement;
    const standaloneMobileApp = Boolean(
      document.body?.classList.contains('app-body')
      && isIosDevice
      && isMobileViewport()
      && (isStandaloneApp || root.classList.contains('standalone-app'))
    );
    root.classList.toggle('ios-standalone-bottom-chrome', standaloneMobileApp);
    document.body?.classList.toggle('ios-standalone-bottom-chrome', standaloneMobileApp);
  };

  const handleMobileViewportChange = () => {
    syncDesktopViewportLock();
    syncMobileViewportClass();
    syncAppViewportHeight();
    syncStandaloneBottomChrome();
  };
  let adaptiveViewportRefreshTimer = 0;
  const scheduleAdaptiveViewportRefresh = () => {
    // Mobile Safari emits several visual viewport resizes while launching and
    // navigating. Those are browser-chrome changes, not layout changes.
    if (isTouchAppDevice()) return;
    window.clearTimeout(adaptiveViewportRefreshTimer);
    adaptiveViewportRefreshTimer = window.setTimeout(handleMobileViewportChange, 120);
  };

  if (isIosDevice) document.body.classList.add('ios-device');
  if (isCoarsePointer) document.body.classList.add('touch-device');
  if (isStandaloneApp) document.body.classList.add('standalone-app');
  if (isStandaloneApp) document.documentElement.classList.add('standalone-app');
  syncDesktopViewportLock({ force: true });
  syncMobileViewportClass();
  if (document.querySelector('.mobile-project-topbar')) document.body.classList.add('has-mobile-project-topbar');
  if (document.querySelector('.account-page')) document.body.classList.add('has-account-page');
  syncStandaloneBottomChrome();
  syncMobileOrientationLockState();
  if (mobileViewportMedia.addEventListener) {
    mobileViewportMedia.addEventListener('change', scheduleAdaptiveViewportRefresh);
  } else if (mobileViewportMedia.addListener) {
    mobileViewportMedia.addListener(scheduleAdaptiveViewportRefresh);
  }
  window.addEventListener('resize', scheduleAdaptiveViewportRefresh, { passive: true });
  let orientationSettleTimer = 0;
  window.addEventListener('orientationchange', () => {
    syncMobileOrientationLockState();
    if (!isTouchAppDevice()) {
      handleMobileViewportChange();
      return;
    }

    // Keep the current page visible while iOS settles the portrait viewport.
    // The landscape-only orientation guard is controlled directly by CSS, so
    // a second full-screen settling cover only causes a blank dark flash when
    // the phone returns to portrait.
    handleMobileViewportChange();
    window.clearTimeout(orientationSettleTimer);
    orientationSettleTimer = window.setTimeout(() => {
      handleMobileViewportChange();
      syncMobileOrientationLockState();
    }, 360);
  }, { passive: true });

  if (isIosDevice) {
    document.addEventListener('gesturestart', event => event.preventDefault(), { passive: false });
    document.addEventListener('gesturechange', event => event.preventDefault(), { passive: false });
    document.addEventListener('gestureend', event => event.preventDefault(), { passive: false });
  }
  const themeColorMeta = document.querySelector('meta[name="theme-color"]');
  const msTileColorMeta = document.querySelector('meta[name="msapplication-TileColor"]');
  const defaultThemeColor = themeColorMeta?.getAttribute('content') || '#8dd62c';
  const authThemeColor = '#f9fbf5';
  const appTopbarThemeColor = '#111820';

  const setThemeColor = value => {
    if (themeColorMeta) themeColorMeta.setAttribute('content', value);
    if (msTileColorMeta) msTileColorMeta.setAttribute('content', value);
  };

  if (document.body.classList.contains('auth-body')) {
    setThemeColor(authThemeColor);
  } else if (document.body.classList.contains('app-body')) {
    setThemeColor(appTopbarThemeColor);
  }

  if (document.body.classList.contains('auth-body')) {
    if (!isMobileViewport() && !isCoarsePointer) {
      const desktopAutofocusField = document.querySelector('[data-desktop-autofocus="1"]');
      window.setTimeout(() => desktopAutofocusField?.focus(), 120);
    }

    if (isIosDevice || isMobileViewport()) {
      const authFieldSelector = '.auth-body input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]), .auth-body textarea, .auth-body select';
      let authViewportBaseHeight = Math.round(window.visualViewport?.height || window.innerHeight || document.documentElement.clientHeight);

      const syncAuthKeyboardState = () => {
        const activeElement = document.activeElement;
        const isTypingField = activeElement instanceof HTMLElement && activeElement.matches(authFieldSelector);
        const viewportHeight = Math.round(window.visualViewport?.height || window.innerHeight || document.documentElement.clientHeight);
        if (!document.body.classList.contains('auth-keyboard-open')) {
          authViewportBaseHeight = Math.max(authViewportBaseHeight || 0, viewportHeight);
        }
        const keyboardOpen = isTypingField || (authViewportBaseHeight - viewportHeight) > 120;
        document.body.classList.toggle('auth-keyboard-open', keyboardOpen);
        if (!keyboardOpen && viewportHeight > authViewportBaseHeight) {
          authViewportBaseHeight = viewportHeight;
        }
      };

      document.addEventListener('focusin', event => {
        const target = event.target;
        if (!(target instanceof HTMLElement) || !target.matches(authFieldSelector)) return;
        document.body.classList.add('auth-keyboard-open');
        window.setTimeout(() => {
          syncAuthKeyboardState();
          target.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' });
        }, 120);
      });

      document.addEventListener('focusout', event => {
        const target = event.target;
        if (!(target instanceof HTMLElement) || !target.matches(authFieldSelector)) return;
        window.setTimeout(syncAuthKeyboardState, 120);
      });

      window.visualViewport?.addEventListener('resize', syncAuthKeyboardState, { passive: true });
      window.addEventListener('orientationchange', () => window.setTimeout(syncAuthKeyboardState, 140), { passive: true });
      window.setTimeout(syncAuthKeyboardState, 0);
    }
  }


  const accountPage = document.querySelector('.account-page');
  if (accountPage && (isIosDevice || isMobileViewport())) {
    const releaseReadonly = input => {
      if (!input) return;
      input.readOnly = false;
      input.removeAttribute('readonly');
    };
    const blurAccountField = () => {
      const active = document.activeElement;
      if (active && accountPage.contains(active) && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)) {
        active.blur();
      }
    };

    accountPage.querySelectorAll('.account-code-row input, .account-2fa-confirm-form input[name="two_factor_code"], .account-2fa-disable-form input[name="two_factor_code"]').forEach(input => {
      input.setAttribute('autocomplete', 'off');
      input.setAttribute('autocorrect', 'off');
      input.setAttribute('autocapitalize', 'off');
      input.setAttribute('spellcheck', 'false');
      input.setAttribute('data-mobile-no-autokeyboard', '1');
      input.readOnly = true;
      input.addEventListener('pointerdown', () => releaseReadonly(input), { once: true });
      input.addEventListener('touchstart', () => releaseReadonly(input), { once: true, passive: true });
      input.addEventListener('keydown', () => releaseReadonly(input), { once: true });
      input.addEventListener('focus', () => {
        if (input.readOnly) window.setTimeout(() => input.blur(), 0);
      });
    });

    window.setTimeout(blurAccountField, 0);
    window.setTimeout(blurAccountField, 180);
    window.setTimeout(blurAccountField, 420);
  }


  document.querySelectorAll('.js-mapping-autosave-form').forEach(form => {
    let timer = null;
    let requestController = null;
    const statusNote = form.closest('.mapping-page')?.querySelector('.js-mapping-save-note');
    const idleText = statusNote?.dataset.idleText || 'Изменения сохраняются автоматически.';
    const setStatus = (text, state = '') => {
      if (!statusNote) return;
      statusNote.textContent = text || idleText;
      statusNote.dataset.state = state || '';
    };
    form.querySelectorAll('input[type="checkbox"]').forEach(input => {
      input.addEventListener('change', () => {
        window.clearTimeout(timer);
        form.classList.add('is-autosaving');
        setStatus(form.dataset.autosaveText || 'Сохраняем...', 'saving');
        timer = window.setTimeout(() => {
          if (requestController) requestController.abort();
          const controller = new AbortController();
          requestController = controller;
          fetch(form.action || window.location.pathname, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
              'Accept': 'application/json',
            },
            signal: controller.signal,
          })
            .then(async response => {
              const data = await response.json().catch(() => ({}));
              if (!response.ok || data.ok === false) {
                throw new Error(data.message || 'Не удалось сохранить распределение');
              }
              setStatus('Сохранено', 'saved');
            })
            .catch(error => {
              if (error.name === 'AbortError') return;
              form.classList.remove('is-autosaving');
              setStatus('Ошибка сохранения. Попробуйте ещё раз.', 'error');
              showCrmNotice(error.message || 'Не удалось сохранить распределение', 'danger');
            })
            .finally(() => {
              if (requestController === controller) {
                requestController = null;
              }
              if (controller.signal.aborted) return;
              form.classList.remove('is-autosaving');
              window.setTimeout(() => {
                if (!form.classList.contains('is-autosaving')) {
                  setStatus(idleText, '');
                }
              }, 1600);
            });
        }, 180);
      });
    });
  });

  const customSelectBootRoot = document.documentElement;
  const finishCustomSelectBoot = () => {
    const isMobileEntrySurface = customSelectBootRoot.matches('.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device');
    if (isMobileEntrySurface) {
      // Mobile pages are rendered at their final coordinates from the first
      // paint. Do not remove/re-add entry-state classes or wait for a synthetic
      // animation: that class churn repainted the header, dock, cards and text
      // on short/empty pages even though mobile entry motion is disabled.
      customSelectBootRoot.classList.remove(
        'crm-custom-select-fallback',
        'crm-custom-select-pending',
        'crm-mobile-entry-skip',
        'crm-page-entry-pending',
        'crm-page-entry-started',
        'crm-mobile-entry-pending',
        'crm-mobile-entry-started'
      );
      customSelectBootRoot.classList.add(
        'crm-custom-select-ready',
        'crm-page-entry-complete',
        'crm-mobile-entry-complete'
      );
      return;
    }
    customSelectBootRoot.classList.remove(
      'crm-custom-select-fallback',
      'crm-mobile-entry-skip',
      'crm-page-entry-pending',
      'crm-page-entry-started',
      'crm-page-entry-complete',
      'crm-mobile-entry-started',
      'crm-mobile-entry-complete'
    );
    customSelectBootRoot.classList.remove('crm-custom-select-pending');
    customSelectBootRoot.classList.add('crm-custom-select-ready');
    customSelectBootRoot.classList.remove('crm-mobile-entry-pending');
  };

  const prepareNativeSelectsForCustomUi = (scope = document) => {
    const excludedSelector = [
      '.developer-custom-select select',
      'select[multiple]',
      'select[size]:not([size="1"])',
      'select[data-native-select]',
      'select[data-no-custom-select]',
      '.flatpickr-monthDropdown-months'
    ].join(',');
    // Native controls are more stable on touch devices: constructing a portal
    // during first paint caused the filter row to reflow and visibly flicker.
    // Apartments filters explicitly opt into the custom UI on mobile too:
    // several mobile browsers ignore CSS font-weight on native selected values.
    const useNativeMobileSelect = true;
    const isMobileSelectUi = document.documentElement.matches('.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device');

    scope.querySelectorAll('select').forEach(select => {
      if (select.matches(excludedSelector)) return;
      if (select.closest('.developer-custom-select')) return;
      if (select.dataset.customSelectReady === '1') return;

      const forceCustomSelectOnMobile = select.hasAttribute('data-force-custom-select')
        || Boolean(select.closest('.apartments-filter-form'))
        || Boolean(select.closest('.contractor-filter-form'));
      if (forceCustomSelectOnMobile) {
        delete select.dataset.nativeSelect;
        select.classList.remove('mobile-native-select');
      }

      if (useNativeMobileSelect && isMobileSelectUi && !forceCustomSelectOnMobile) {
        select.dataset.nativeSelect = '1';
        select.classList.add('mobile-native-select');
        return;
      }

      const shell = document.createElement('div');
      shell.className = 'developer-custom-select js-developer-custom-select global-custom-select';
      if (select.className) shell.classList.add('global-custom-select-inherited');
      select.parentNode.insertBefore(shell, select);
      shell.appendChild(select);
      select.dataset.customSelectReady = '1';
      select.classList.add('developer-native-select');
    });
  };

  const initDeveloperCustomSelects = (scope = document) => {
    prepareNativeSelectsForCustomUi(scope);
    const isMobileSelectUi = document.documentElement.matches('.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device');

    scope.querySelectorAll('.js-developer-custom-select').forEach(selectShell => {
      const select = selectShell.querySelector('select');
      if (!select) return;
      const forceCustomSelectOnMobile = select.hasAttribute('data-force-custom-select')
        || Boolean(select.closest('.apartments-filter-form'))
        || Boolean(select.closest('.contractor-filter-form'));
      if (forceCustomSelectOnMobile) {
        delete select.dataset.nativeSelect;
        select.classList.remove('mobile-native-select');
      }
      if (isMobileSelectUi && !forceCustomSelectOnMobile) {
        select.classList.add('mobile-native-select');
        select.tabIndex = 0;
        select.removeAttribute('aria-hidden');
        select.classList.remove('developer-native-select');
        selectShell.querySelectorAll('.developer-select-button').forEach(button => button.remove());
        selectShell.classList.remove('is-open');
        return;
      }
      if (selectShell.querySelector('.developer-select-button')) return;

      select.tabIndex = -1;
      select.setAttribute('aria-hidden', 'true');
      select.classList.add('developer-native-select');

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'developer-select-button';
      button.setAttribute('aria-haspopup', 'listbox');
      button.setAttribute('aria-expanded', 'false');

      const valueText = document.createElement('span');
      valueText.className = 'developer-select-value';
      const arrow = document.createElement('span');
      arrow.className = 'developer-select-arrow';
      arrow.setAttribute('aria-hidden', 'true');
      arrow.innerHTML = '<i class="bi bi-chevron-down"></i>';
      button.append(valueText, arrow);

      const menu = document.createElement('div');
      menu.className = 'developer-select-menu developer-select-menu-portal';
      menu.setAttribute('role', 'listbox');
      menu.setAttribute('data-select-portal', '1');
      menu.hidden = true;

      const closeSelect = () => {
        selectShell.classList.remove('is-open');
        menu.classList.remove('is-portal-open', 'is-above');
        menu.hidden = true;
        button.setAttribute('aria-expanded', 'false');
        window.removeEventListener('scroll', placeMenu, true);
        window.removeEventListener('resize', placeMenu);
      };

      const closeOtherSelects = () => {
        document.querySelectorAll('.js-developer-custom-select.is-open').forEach(opened => {
          if (opened === selectShell) return;
          opened.classList.remove('is-open');
          const openedButton = opened.querySelector('.developer-select-button');
          if (openedButton) openedButton.setAttribute('aria-expanded', 'false');
        });
        document.querySelectorAll('.developer-select-menu-portal.is-portal-open').forEach(openedMenu => {
          if (openedMenu === menu) return;
          openedMenu.classList.remove('is-portal-open', 'is-above');
          openedMenu.hidden = true;
        });
      };

      const options = Array.from(select.options).map(option => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'developer-select-option';
        item.setAttribute('role', 'option');
        item.dataset.value = option.value;
        item.textContent = option.textContent;
        item.disabled = option.disabled;
        item.addEventListener('click', () => {
          if (option.disabled) return;
          select.value = option.value;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          setActiveOption();
          closeSelect();
          button.focus({ preventScroll: true });
        });
        menu.appendChild(item);
        return item;
      });

      const currentOption = () => select.options[select.selectedIndex] || select.options[0];
      function setActiveOption() {
        const selected = currentOption();
        valueText.textContent = selected ? selected.textContent : '';
        options.forEach(item => {
          const option = Array.from(select.options).find(opt => opt.value === item.dataset.value);
          const isActive = item.dataset.value === select.value;
          item.disabled = Boolean(option?.disabled);
          item.classList.toggle('is-selected', isActive);
          item.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
      }

      function placeMenu() {
        if (!selectShell.classList.contains('is-open')) return;
        const rect = button.getBoundingClientRect();
        const mobileLikeSelectUi = document.documentElement.matches('.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device');
        const viewportGap = mobileLikeSelectUi ? 10 : 12;
        const mobileBottomNav = mobileLikeSelectUi ? document.querySelector('.mobile-bottom-nav') : null;
        const bottomNavRect = mobileBottomNav?.getBoundingClientRect?.();
        const bottomNavInset = bottomNavRect
          ? Math.max(0, window.innerHeight - Math.max(0, bottomNavRect.top))
          : 0;
        const minWidth = Math.max(rect.width, mobileLikeSelectUi ? 220 : 180);
        const availableBelow = Math.max(0, window.innerHeight - bottomNavInset - rect.bottom - viewportGap);
        const availableAbove = Math.max(0, rect.top - viewportGap);
        const estimatedHeight = Math.min(300, Math.max(46, options.length * 42 + 18));
        const measuredHeight = menu.scrollHeight ? Math.min(300, Math.max(46, menu.scrollHeight)) : estimatedHeight;
        // Выпадающий список по умолчанию открываем вниз, чтобы он не налезал на поле и кнопки сверху.
        // Вверх открываем только когда снизу совсем мало места, иначе ограничиваем высоту и даем прокрутку.
        const openAbove = availableBelow < 96 && availableAbove > availableBelow + 80;
        const available = Math.max(96, (openAbove ? availableAbove : availableBelow) - (mobileLikeSelectUi ? 2 : 8));
        const maxHeight = Math.max(96, Math.min(mobileLikeSelectUi ? 320 : 300, available));
        const menuHeight = Math.min(measuredHeight, maxHeight);
        const left = Math.min(
          Math.max(viewportGap, rect.left),
          Math.max(viewportGap, window.innerWidth - minWidth - viewportGap),
        );
        const top = openAbove
          ? Math.max(viewportGap, rect.top - menuHeight - 8)
          : Math.max(viewportGap, Math.min(window.innerHeight - bottomNavInset - viewportGap - menuHeight, rect.bottom + 8));
        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
        menu.style.width = `${minWidth}px`;
        menu.style.maxHeight = `${maxHeight}px`;
        menu.style.setProperty('--developer-select-mobile-bottom-gap', `${bottomNavInset}px`);
        menu.classList.toggle('is-above', openAbove);
      }

      const openSelect = () => {
        closeOtherSelects();
        if (!menu.isConnected) document.body.appendChild(menu);
        setActiveOption();
        selectShell.classList.add('is-open');
        button.setAttribute('aria-expanded', 'true');
        menu.hidden = false;
        menu.classList.add('is-portal-open');
        placeMenu();
        window.addEventListener('scroll', placeMenu, true);
        window.addEventListener('resize', placeMenu);
        const activeItem = menu.querySelector('.developer-select-option.is-selected:not(:disabled)') || menu.querySelector('.developer-select-option:not(:disabled)');
        window.setTimeout(() => activeItem?.focus({ preventScroll: true }), 0);
      };

      button.addEventListener('click', () => {
        if (selectShell.classList.contains('is-open')) closeSelect();
        else openSelect();
      });

      button.addEventListener('keydown', event => {
        if (['ArrowDown', 'Enter', ' '].includes(event.key)) {
          event.preventDefault();
          openSelect();
        }
      });

      menu.addEventListener('keydown', event => {
        const enabledOptions = options.filter(item => !item.disabled);
        const currentIndex = enabledOptions.indexOf(document.activeElement);
        if (event.key === 'Escape') {
          event.preventDefault();
          closeSelect();
          button.focus({ preventScroll: true });
        }
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          const next = enabledOptions[Math.min(currentIndex + 1, enabledOptions.length - 1)] || enabledOptions[0];
          next?.focus({ preventScroll: true });
        }
        if (event.key === 'ArrowUp') {
          event.preventDefault();
          const prev = enabledOptions[Math.max(currentIndex - 1, 0)] || enabledOptions[0];
          prev?.focus({ preventScroll: true });
        }
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          if (document.activeElement?.classList.contains('developer-select-option')) document.activeElement.click();
        }
      });

      select.addEventListener('change', setActiveOption);
      selectShell.appendChild(button);
      setActiveOption();
    });
  };

  const refreshCustomSelectViewportMode = (scope = document) => {
    const currentMode = document.documentElement.matches('.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device') ? 'mobile' : 'desktop';
    if (lastCustomSelectViewportMode === currentMode && scope === document) return;
    lastCustomSelectViewportMode = currentMode;

    document.querySelectorAll('.js-developer-custom-select').forEach(selectShell => {
      const select = selectShell.querySelector('select');
      if (!select) return;
      const forceCustomSelectOnMobile = select.hasAttribute('data-force-custom-select')
        || Boolean(select.closest('.apartments-filter-form'))
        || Boolean(select.closest('.contractor-filter-form'));

      if (currentMode === 'mobile' && !forceCustomSelectOnMobile) {
        select.classList.add('mobile-native-select');
        select.classList.remove('developer-native-select');
        select.tabIndex = 0;
        select.removeAttribute('aria-hidden');
        selectShell.querySelectorAll('.developer-select-button').forEach(button => button.remove());
        selectShell.classList.remove('is-open');
        return;
      }
    });

    initDeveloperCustomSelects(scope);
  };

  initDeveloperCustomSelects();
  refreshCustomSelectViewportMode();
  finishCustomSelectBoot();
  window.addEventListener('resize', () => refreshCustomSelectViewportMode(), { passive: true });

  document.addEventListener('click', event => {
    if (event.target.closest('.js-developer-custom-select') || event.target.closest('.developer-select-menu-portal')) return;
    document.querySelectorAll('.js-developer-custom-select.is-open').forEach(selectShell => {
      selectShell.classList.remove('is-open');
      const button = selectShell.querySelector('.developer-select-button');
      if (button) button.setAttribute('aria-expanded', 'false');
    });
    document.querySelectorAll('.developer-select-menu-portal.is-portal-open').forEach(menu => {
      menu.classList.remove('is-portal-open', 'is-above');
      menu.hidden = true;
    });
  });

  const customSelectObserver = new MutationObserver(mutations => {
    mutations.forEach(mutation => {
      mutation.addedNodes.forEach(node => {
        if (node.nodeType !== 1) return;
        if (node.matches?.('select, .js-developer-custom-select') || node.querySelector?.('select, .js-developer-custom-select')) {
          refreshCustomSelectViewportMode(node.matches?.('select') ? node.parentElement || document : node);
        }
      });
    });
  });
  customSelectObserver.observe(document.body, { childList: true, subtree: true });

  const initTooltips = () => {
    if (isMobileViewport()) return;
    if (!(window.bootstrap && bootstrap.Tooltip)) return;
    document.querySelectorAll('[title]').forEach(el => {
      if (!bootstrap.Tooltip.getInstance(el)) new bootstrap.Tooltip(el);
    });
  };

  if (window.requestAnimationFrame) {
    window.requestAnimationFrame(() => window.setTimeout(initTooltips, 0));
  } else {
    window.setTimeout(initTooltips, 0);
  }

  const restoreSafeSubmitButton = button => {
    if (!button || !button.dataset.originalHtml) return;
    button.innerHTML = button.dataset.originalHtml;
    button.disabled = button.dataset.originalDisabled === '1';
    button.classList.remove('disabled');
    button.removeAttribute('aria-disabled');
    button.style.pointerEvents = '';
  };

  document.querySelectorAll('.js-auth-safe-submit').forEach(form => {
    const submitButton = form.querySelector('.js-auth-submit-button, button[type="submit"], input[type="submit"]');
    if (!submitButton) return;
    submitButton.dataset.originalHtml = submitButton.innerHTML || submitButton.value || '';
    submitButton.dataset.originalDisabled = submitButton.disabled ? '1' : '0';

    form.addEventListener('submit', () => {
      window.setTimeout(() => {
        if (!form.checkValidity()) {
          restoreSafeSubmitButton(submitButton);
          return;
        }
        const loadingText = form.dataset.loadingText || submitButton.dataset.loadingText || 'Отправляем...';
        submitButton.disabled = true;
        submitButton.classList.add('disabled');
        submitButton.setAttribute('aria-disabled', 'true');
        submitButton.innerHTML = `<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>${loadingText}`;
      }, 0);
    });
  });

  document.querySelectorAll('.registration-request-modal').forEach(form => {
    const detailsStep = form.querySelector('[data-registration-step="details"]');
    const captchaStep = form.querySelector('[data-registration-step="captcha"]');
    const detailFields = Array.from(form.querySelectorAll('[data-registration-detail]'));
    const captchaField = form.querySelector('#registrationCaptcha');
    const nextButton = form.querySelector('.js-registration-next');
    const backButton = form.querySelector('.js-registration-back');
    const modalElement = form.closest('.modal');

    const setStep = step => {
      const isCaptcha = step === 'captcha';
      detailsStep?.classList.toggle('is-active', !isCaptcha);
      captchaStep?.classList.toggle('is-active', isCaptcha);
      if (isCaptcha) {
        window.setTimeout(() => captchaField?.focus(), 150);
      } else {
        window.setTimeout(() => detailFields[0]?.focus(), 150);
      }
    };

    const validateDetails = () => {
      let ok = true;
      detailFields.forEach(field => {
        const valid = field.checkValidity();
        field.classList.toggle('is-invalid', !valid);
        if (!valid) ok = false;
      });
      if (!ok) detailFields.find(field => !field.checkValidity())?.focus();
      return ok;
    };

    detailFields.forEach(field => {
      field.addEventListener('input', () => {
        if (field.checkValidity()) field.classList.remove('is-invalid');
      });
    });

    nextButton?.addEventListener('click', () => {
      if (validateDetails()) setStep('captcha');
    });
    backButton?.addEventListener('click', () => setStep('details'));

    form.addEventListener('keydown', event => {
      if (event.key !== 'Enter' || !detailsStep?.classList.contains('is-active')) return;
      event.preventDefault();
      if (validateDetails()) setStep('captcha');
    });

    modalElement?.addEventListener('hidden.bs.modal', () => {
      setStep('details');
      form.querySelectorAll('.is-invalid').forEach(field => field.classList.remove('is-invalid'));
      restoreSafeSubmitButton(form.querySelector('.js-auth-submit-button'));
    });
  });

  window.addEventListener('pageshow', () => {
    document.querySelectorAll('.js-auth-submit-button').forEach(restoreSafeSubmitButton);
  });

  document.querySelectorAll('.js-settings-autosave').forEach(form => {
    let saveTimer = null;
    const syncSectionLockState = checkbox => {
      const item = checkbox.closest('.settings-section-lock');
      if (!item) return;
      item.classList.toggle('is-active', checkbox.checked);
      const status = item.querySelector('.settings-section-lock-copy small');
      if (status) status.textContent = checkbox.checked ? 'Сейчас раздел закрыт' : 'Раздел открыт';
    };
    const save = async () => {
      try {
        const response = await fetch(form.action || window.location.href, {
          method: 'POST',
          body: new FormData(form),
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
          },
          credentials: 'same-origin'
        });
        if (!response.ok) throw new Error('settings save failed');
        const data = await response.json().catch(() => ({}));
        if (data.ok === false) throw new Error('settings save rejected');
      } catch (error) {
        showCrmNotice('Не удалось сохранить настройку. Попробуйте ещё раз.', 'danger');
      }
    };
    form.addEventListener('change', event => {
      const control = event.target.closest('input[type="checkbox"]');
      if (!control) return;
      syncSectionLockState(control);
      window.clearTimeout(saveTimer);
      saveTimer = window.setTimeout(save, 120);
    });
  });

  const getCsrfToken = () => {
    const el = document.querySelector('input[name="csrf_token"]');
    return el ? el.value : '';
  };

  const trackOpenedTabVisit = () => {
    const analyticsUrl = document.body?.dataset?.tabVisitUrl;
    if (!analyticsUrl || !window.sessionStorage) return;
    try {
      let tabId = sessionStorage.getItem('crm-tab-visit-id');
      if (!tabId) {
        const randomPart = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        tabId = `tab-${randomPart}`;
        sessionStorage.setItem('crm-tab-visit-id', tabId);
      }
      const sentKey = `crm-tab-visit-sent:${tabId}`;
      if (sessionStorage.getItem(sentKey) === '1') return;
      sessionStorage.setItem(sentKey, '1');

      const payload = JSON.stringify({
        tab_id: tabId,
        path: `${window.location.pathname}${window.location.search}`,
        referrer: document.referrer || '',
      });
      const beaconBody = new Blob([payload], { type: 'application/json' });
      const queued = typeof navigator.sendBeacon === 'function' && navigator.sendBeacon(analyticsUrl, beaconBody);
      if (!queued) {
        fetch(analyticsUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
          credentials: 'same-origin',
          keepalive: true,
          body: payload,
        }).catch(() => {
          sessionStorage.removeItem(sentKey);
        });
      }
    } catch (error) {}
  };

  trackOpenedTabVisit();

  try {
    if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual';
  } catch (error) {}

  const scrollStateKey = `crm-scroll:${window.location.pathname}${window.location.search}`;
  const scrollLastStateKey = 'crm-scroll:last';
  const statisticsOverviewTopKey = 'crm-statistics:force-overview-top';
  const pageScrollRootSelectors = [
    '.app-content',
    '.objects-content',
    '.documents-content',
    '.documents-standalone-content',
  ];
  const reloadFocusResetSelectors = [
    '.crm-filter-form',
    '.assignment-search-form',
    '.assignment-smart-form',
    '.assignment-report-filter-form',
    '.glass-filter-form',
    '.materials-filter-form',
    '.apartments-filter-form',
    '.remarks-filter-form',
  ];
  const getNavigationType = () => {
    try {
      const navEntry = window.performance?.getEntriesByType?.('navigation')?.[0];
      if (navEntry && typeof navEntry.type === 'string' && navEntry.type) return navEntry.type;
      const legacyType = window.performance?.navigation?.type;
      if (legacyType === 1) return 'reload';
      if (legacyType === 2) return 'back_forward';
    } catch (error) {}
    return 'navigate';
  };
  const navigationType = getNavigationType();
  let scrollRestoreInProgress = false;
  let scrollRestoreTimer = null;
  let reloadTopResetTimer = null;
  let lastScrollRestoreSignature = '';
  const getPageScrollContainers = () => {
    const containers = [];
    const append = container => {
      if (!container || containers.includes(container)) return;
      containers.push(container);
    };
    append(document.scrollingElement);
    append(document.documentElement);
    append(document.body);
    pageScrollRootSelectors.forEach(selector => append(document.querySelector(selector)));
    return containers;
  };
  const readPageScrollPosition = () => {
    let bestX = window.scrollX || window.pageXOffset || 0;
    let bestY = window.scrollY || window.pageYOffset || 0;
    getPageScrollContainers().forEach(container => {
      const x = Number(container.scrollLeft || 0);
      const y = Number(container.scrollTop || 0);
      if (Math.abs(y) > Math.abs(bestY) || (Math.abs(y) === Math.abs(bestY) && Math.abs(x) > Math.abs(bestX))) {
        bestX = x;
        bestY = y;
      }
    });
    return { x: bestX, y: bestY };
  };
  const writePageScrollPosition = (x = 0, y = 0) => {
    try {
      window.scrollTo(x, y);
    } catch (error) {}
    getPageScrollContainers().forEach(container => {
      if (Math.abs(Number(container.scrollLeft || 0) - x) >= 1) container.scrollLeft = x;
      if (Math.abs(Number(container.scrollTop || 0) - y) >= 1) container.scrollTop = y;
    });
  };
  const clearRememberedScrollPosition = () => {
    try {
      sessionStorage.removeItem(scrollStateKey);
      sessionStorage.removeItem(scrollLastStateKey);
    } catch (error) {}
  };
  const finishScrollRestore = () => {
    scrollRestoreInProgress = false;
    if (scrollRestoreTimer) {
      window.clearTimeout(scrollRestoreTimer);
      scrollRestoreTimer = null;
    }
  };
  const forceTopAfterReload = () => {
    if (navigationType !== 'reload') return;
    if (reloadTopResetTimer) {
      window.clearTimeout(reloadTopResetTimer);
      reloadTopResetTimer = null;
    }
    let attempts = 0;
    const blurReloadFocusedField = () => {
      const activeElement = document.activeElement;
      if (!(activeElement instanceof HTMLElement)) return;
      if (!activeElement.matches('input, select, textarea, [contenteditable="true"]')) return;
      if (!activeElement.closest(reloadFocusResetSelectors.join(','))) return;
      activeElement.blur();
    };
    const applyTop = () => {
      blurReloadFocusedField();
      writePageScrollPosition(0, 0);
      attempts += 1;
      const currentPosition = readPageScrollPosition();
      if (Math.abs(currentPosition.y) < 2 && attempts >= 2) return;
      if (attempts >= 14) return;
      reloadTopResetTimer = window.setTimeout(applyTop, attempts < 4 ? 80 : 180);
    };
    requestAnimationFrame(applyTop);
  };
  const requestStatisticsOverviewTop = () => {
    try {
      sessionStorage.setItem(statisticsOverviewTopKey, '1');
    } catch (error) {}
  };
  window.requestStatisticsOverviewTop = requestStatisticsOverviewTop;
  const consumeStatisticsOverviewTopRequest = () => {
    try {
      if (sessionStorage.getItem(statisticsOverviewTopKey) !== '1') return false;
      sessionStorage.removeItem(statisticsOverviewTopKey);
      return true;
    } catch (error) {
      return false;
    }
  };
  const rememberScrollPosition = (reason = 'manual') => {
    try {
      const now = Date.now();
      let effectiveReason = reason || 'manual';
      if (effectiveReason === 'unload') {
        const existingRaw = sessionStorage.getItem(scrollStateKey) || sessionStorage.getItem(scrollLastStateKey);
        if (existingRaw) {
          const existingState = JSON.parse(existingRaw);
          const shouldPreserveRecentReason = existingState
            && existingState.path === window.location.pathname
            && existingState.search === window.location.search
            && typeof existingState.reason === 'string'
            && existingState.reason
            && existingState.reason !== 'unload'
            && (now - Number(existingState.ts || 0)) < 1600;
          if (shouldPreserveRecentReason) effectiveReason = existingState.reason;
        }
      }
      const state = {
        path: window.location.pathname,
        search: window.location.search,
        ...readPageScrollPosition(),
        ts: now,
        reason: effectiveReason,
      };
      const encoded = JSON.stringify(state);
      sessionStorage.setItem(scrollStateKey, encoded);
      sessionStorage.setItem(scrollLastStateKey, encoded);
    } catch (error) {}
  };

  const restoreScrollPosition = () => {
    if (scrollRestoreInProgress) return;
    try {
      const raw = sessionStorage.getItem(scrollStateKey) || sessionStorage.getItem(scrollLastStateKey);
      if (!raw) return;
      const state = JSON.parse(raw);
      if (!state || typeof state.y !== 'number') return;
      if ((state.path && state.path !== window.location.pathname) || (state.search && state.search !== window.location.search)) {
        sessionStorage.removeItem(scrollLastStateKey);
        return;
      }
      if (Date.now() - Number(state.ts || 0) > 45000) {
        sessionStorage.removeItem(scrollStateKey);
        sessionStorage.removeItem(scrollLastStateKey);
        return;
      }
      const restoreReason = typeof state.reason === 'string' ? state.reason : '';
      const restoreSignature = `${state.path || ''}|${state.search || ''}|${state.ts || ''}|${restoreReason}`;
      // A plain refresh should reopen the page steadily instead of snapping back
      // to a saved scroll position near the search/filter form.
      if (navigationType === 'reload') {
        clearRememberedScrollPosition();
        return;
      }
      if (restoreSignature === lastScrollRestoreSignature) return;
      const targetX = state.x || 0;
      const targetY = state.y || 0;
      const currentPosition = readPageScrollPosition();
      if (Math.abs(currentPosition.x - targetX) < 4 && Math.abs(currentPosition.y - targetY) < 4) {
        clearRememberedScrollPosition();
        return;
      }
      lastScrollRestoreSignature = restoreSignature;
      scrollRestoreInProgress = true;
      let attempts = 0;
      const applyScroll = () => {
        writePageScrollPosition(targetX, targetY);
        attempts += 1;
        const restoredPosition = readPageScrollPosition();
        const reachedTarget = Math.abs(restoredPosition.x - targetX) < 4 && Math.abs(restoredPosition.y - targetY) < 4;
        if (reachedTarget || attempts >= 30) {
          clearRememberedScrollPosition();
          finishScrollRestore();
          return;
        }
        scrollRestoreTimer = window.setTimeout(applyScroll, 150);
      };
      requestAnimationFrame(applyScroll);
    } catch (error) {
      finishScrollRestore();
    }
  };

  // Restore saved scroll only for real history traversal. For ordinary loads,
  // refreshes, and in-app navigations it causes visible jumps around filters.
  if (navigationType !== 'back_forward') {
    clearRememberedScrollPosition();
  }
  forceTopAfterReload();
  const normalizeStatisticsOverviewPosition = () => {
    if (!document.querySelector('.developer-statistics-page-overview')) return;
    const shouldForceTop = consumeStatisticsOverviewTopRequest() || window.location.hash === '#overview-chart';
    if (!shouldForceTop) return;
    clearRememberedScrollPosition();
    if (window.location.hash) {
      history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
    }
    const applyTop = () => {
      writePageScrollPosition(0, 0);
    };
    requestAnimationFrame(applyTop);
    window.setTimeout(applyTop, 90);
    window.setTimeout(applyTop, 260);
  };
  normalizeStatisticsOverviewPosition();
  window.addEventListener('pageshow', event => {
    if (!event.persisted && getNavigationType() !== 'back_forward') return;
    finishScrollRestore();
    lastScrollRestoreSignature = '';
    restoreScrollPosition();
  });
  window.addEventListener('load', normalizeStatisticsOverviewPosition);
  window.addEventListener('pageshow', normalizeStatisticsOverviewPosition);
  window.addEventListener('load', forceTopAfterReload);
  window.addEventListener('pageshow', forceTopAfterReload);
  window.addEventListener('beforeunload', () => rememberScrollPosition('unload'));
  window.addEventListener('pagehide', () => rememberScrollPosition('unload'));
  document.addEventListener('submit', event => {
    if (event.target instanceof HTMLFormElement) rememberScrollPosition('submit');
  }, true);
  document.addEventListener('click', event => {
    const submitButton = event.target.closest('button[type="submit"], input[type="submit"]');
    if (submitButton) rememberScrollPosition('submit');
    const link = event.target.closest('a[href]');
    if (!link) return;
    if (link.dataset.noScrollRestore === '1') {
      clearRememberedScrollPosition();
      return;
    }
    const href = link.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
    try {
      const targetUrl = new URL(href, window.location.href);
      if (targetUrl.origin === window.location.origin) rememberScrollPosition('link');
    } catch (error) {}
  }, true);
  document.addEventListener('click', event => {
    const hashLink = event.target.closest('a[href="#"]');
    if (hashLink) event.preventDefault();
  });

  const showCrmNotice = (message, category = 'warning') => {
    const safeCategory = ['success', 'warning', 'danger', 'info'].includes(category) ? category : 'info';
    let stack = document.querySelector('.crm-toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'flash-stack crm-toast-stack';
      stack.setAttribute('aria-live', 'polite');
      stack.setAttribute('aria-atomic', 'true');
      document.body.appendChild(stack);
    }
    const titles = { success: 'Готово', warning: 'Внимание', danger: 'Ошибка', info: 'Информация' };
    const icons = { success: 'bi-check2-circle', warning: 'bi-exclamation-triangle', danger: 'bi-x-circle', info: 'bi-info-circle' };
    const toast = document.createElement('div');
    toast.className = `alert alert-${safeCategory} alert-dismissible fade show crm-toast crm-toast-${safeCategory}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
      <div class="crm-toast-icon"><i class="bi ${icons[safeCategory]}"></i></div>
      <div class="crm-toast-body">
        <div class="crm-toast-title">${titles[safeCategory]}</div>
        <div class="crm-toast-text">${escapeHtml(String(message || '')).replace(/\r?\n/g, '<br>')}</div>
      </div>
      <button type="button" class="crm-toast-close" aria-label="Закрыть"><i class="bi bi-x-lg"></i></button>
    `;
    stack.appendChild(toast);
    const close = () => toast.remove();
    toast.querySelector('.crm-toast-close')?.addEventListener('click', close);
    window.setTimeout(close, 4500);
  };
  window.showCrmNotice = showCrmNotice;

  const moveDoneItemToBottom = () => {
    // Строки больше не переставляются сразу после изменения статуса.
    // Серверная сортировка применится только после обновления страницы/таблицы.
  };
  window.moveDoneItemToBottom = moveDoneItemToBottom;


  const escapeRegExp = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const escapeHtml = value => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

  const showSiteEntryNoticeOnce = () => {
    const storageKey = 'crm-site-entry-notice-v2';
    const isAppPage = document.body.classList.contains('app-body');
    if (!isAppPage) {
      try {
        window.sessionStorage.removeItem(storageKey);
      } catch (error) {
        delete document.body.dataset.siteEntryNoticeShown;
      }
      return;
    }
    try {
      if (window.sessionStorage.getItem(storageKey) === '1') return;
      window.sessionStorage.setItem(storageKey, '1');
    } catch (error) {
      if (document.body.dataset.siteEntryNoticeShown === '1') return;
      document.body.dataset.siteEntryNoticeShown = '1';
    }
    showCrmNotice('Добро пожаловать!\nCRM от Худовердиева В.С.', 'success');
  };

  const viewportTransitionLoader = document.querySelector('.viewport-transition-loader');
  const canShowViewportTransitionLoader = () => false;

  const showViewportTransitionLoader = () => {
    if (!canShowViewportTransitionLoader()) return;
    viewportTransitionLoader.style.removeProperty('display');
    viewportTransitionLoader.style.pointerEvents = 'auto';
    viewportTransitionLoader.classList.remove('is-hidden');
  };

  const navigateWithViewportTransition = href => {
    if (!href) return;
    rememberInstantMobileEntryForNextNavigation(href);
    showViewportTransitionLoader();
    window.location.href = href;
  };

  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link) return;
    if ((link.getAttribute('target') || '').toLowerCase() === '_blank') return;
    if (link.hasAttribute('download') || link.dataset.noLoader === '1') return;
    if (link.dataset.bsToggle || link.dataset.bsDismiss) return;
    const href = link.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
    try {
      const targetUrl = new URL(href, window.location.href);
      const currentUrl = new URL(window.location.href);
      if (targetUrl.origin !== currentUrl.origin) return;
      if (`${targetUrl.pathname}${targetUrl.search}${targetUrl.hash}` === `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`) return;
      rememberInstantMobileEntryForNextNavigation(targetUrl.href);
      if (canShowViewportTransitionLoader()) showViewportTransitionLoader();
    } catch (error) {}
  }, true);

  showSiteEntryNoticeOnce();

  const applyHighlightToEscaped = (html, regex) => {
    if (!regex) return html;
    return html.replace(regex, '<mark class="search-highlight">$1</mark>');
  };

  const formatRemarkHtml = (value, regex = null) => {
    const text = String(value || '');
    if (!text) return '';
    const pairs = { '"': '"', '«': '»', '“': '”', '„': '“', '‹': '›' };
    const stack = [];
    const ranges = [];
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      if (Object.prototype.hasOwnProperty.call(pairs, char)) {
        if (char === '"' && stack.length && stack[stack.length - 1].close === char) {
          const item = stack.pop();
          if (i > item.start) ranges.push([item.start, i + 1]);
        } else {
          stack.push({ close: pairs[char], start: i });
        }
        continue;
      }
      if (stack.length && char === stack[stack.length - 1].close) {
        const item = stack.pop();
        if (i > item.start) ranges.push([item.start, i + 1]);
      }
    }
    ranges.sort((a, b) => a[0] - b[0]);
    if (!ranges.length) return applyHighlightToEscaped(escapeHtml(text), regex);

    let pos = 0;
    let html = '';
    ranges.forEach(([start, end]) => {
      if (start < pos) return;
      if (start > pos) html += applyHighlightToEscaped(escapeHtml(text.slice(pos, start)), regex);
      html += `<span class="remark-quoted-strike">${applyHighlightToEscaped(escapeHtml(text.slice(start, end)), regex)}</span>`;
      pos = end;
    });
    if (pos < text.length) html += applyHighlightToEscaped(escapeHtml(text.slice(pos)), regex);
    return html;
  };


  const showCrmConfirm = (options = {}) => new Promise(resolve => {
    const settings = typeof options === 'string' ? { message: options } : options;
    const title = settings.title || 'Подтвердите действие';
    const message = settings.message || 'Подтвердите действие';
    const okText = settings.okText || 'Подтвердить';
    const cancelText = settings.cancelText || 'Отмена';
    const danger = settings.danger !== false;

    let modal = document.querySelector('.js-crm-assignment-confirm-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.className = 'crm-confirm-overlay assignment-confirm-overlay js-crm-assignment-confirm-modal d-none';
      modal.innerHTML = `
        <div class="crm-confirm-card assignment-confirm-card" role="dialog" aria-modal="true" aria-labelledby="assignment-confirm-title" aria-describedby="assignment-confirm-text">
          <div class="confirm-modal-icon"><i class="bi bi-person-dash"></i></div>
          <h2 id="assignment-confirm-title" class="js-assignment-confirm-title">Подтвердите действие</h2>
          <p id="assignment-confirm-text" class="js-assignment-confirm-text">Подтвердите действие</p>
          <div class="modal-actions">
            <button class="btn btn-danger js-assignment-confirm-ok" type="button">Подтвердить</button>
            <button class="btn btn-outline-secondary js-assignment-confirm-cancel" type="button">Отмена</button>
          </div>
        </div>`;
      document.body.appendChild(modal);
    }

    const titleEl = modal.querySelector('.js-assignment-confirm-title');
    const textEl = modal.querySelector('.js-assignment-confirm-text');
    const cancel = modal.querySelector('.js-assignment-confirm-cancel');
    const ok = modal.querySelector('.js-assignment-confirm-ok');
    if (titleEl) titleEl.textContent = title;
    if (textEl) textEl.textContent = message;
    if (cancel) cancel.textContent = cancelText;
    if (ok) {
      ok.textContent = okText;
      ok.className = `btn ${danger ? 'btn-danger' : 'btn-primary'} js-assignment-confirm-ok`;
    }

    let settled = false;
    const close = result => {
      if (settled) return;
      settled = true;
      modal.classList.add('d-none');
      modal.removeEventListener('click', onBackdropClick);
      document.removeEventListener('keydown', onKeydown);
      resolve(result);
    };
    const onBackdropClick = event => {
      if (event.target === modal) close(false);
    };
    const onKeydown = event => {
      if (event.key === 'Escape') close(false);
    };

    if (cancel) cancel.onclick = () => close(false);
    if (ok) ok.onclick = () => close(true);
    modal.addEventListener('click', onBackdropClick);
    document.addEventListener('keydown', onKeydown);
    modal.classList.remove('d-none');
    window.setTimeout(() => cancel?.focus(), 0);
  });
  // Assignment actions are initialized in a separate DOM-ready block below.
  // Expose the shared dialog explicitly instead of relying on block scope.
  window.crmShowConfirm = showCrmConfirm;

  document.querySelectorAll('[data-search-highlight]').forEach(container => {
    const query = (container.dataset.searchHighlight || '').trim();
    if (!query) return;
    let regex;
    try {
      regex = new RegExp(`(${escapeRegExp(query)})`, 'gi');
    } catch (e) {
      return;
    }
    container.querySelectorAll('.js-highlight-text').forEach(el => {
      const raw = el.textContent || '';
      if (!raw.trim()) return;
      el.innerHTML = formatRemarkHtml(raw, regex);
    });
  });

  document.querySelectorAll('.task-table-shell[data-search-query]').forEach(shell => {
    const query = (shell.dataset.searchQuery || '').trim();
    if (!query) return;
    let regex;
    try {
      regex = new RegExp(`(${escapeRegExp(query)})`, 'gi');
    } catch (e) {
      return;
    }
    shell.querySelectorAll('.task-text .inline-text').forEach(el => {
      const raw = el.textContent || '';
      el.innerHTML = formatRemarkHtml(raw, regex);
    });
  });

  document.querySelectorAll('.inline-edit').forEach(btn => {
    btn.addEventListener('click', async () => {
      const taskId = btn.dataset.taskId;
      const span = document.querySelector(`.inline-text[data-task-id="${taskId}"]`);
      if (!span) return;
      if (span.dataset.editing === '1') return;

      if (activeInlineEditor) {
        activeInlineEditor.close();
      }

      span.dataset.editing = '1';
      const current = span.textContent || '';
      const editor = document.createElement('div');
      editor.className = 'inline-editor inline-editor-floating';
      editor.innerHTML = `
        <textarea class="form-control" rows="3"></textarea>
        <div class="inline-editor-actions">
          <button class="btn btn-primary btn-sm" type="button">Сохранить</button>
          <button class="btn btn-outline-secondary btn-sm" type="button">Отмена</button>
        </div>
      `;

      const textarea = editor.querySelector('textarea');
      const saveBtn = editor.querySelector('.btn-primary');
      const cancelBtn = editor.querySelector('.btn-outline-secondary');
      const host = span.closest('.inline-editor-anchor') || span.closest('.task-text') || span.parentElement;
      const row = span.closest('tr, .glass-order-card, .apartment-task-item, .related-task-item');
      if (!host) return;

      textarea.value = current;
      host.classList.add('inline-editing-host');
      row?.classList.add('inline-editor-open-row');
      host.appendChild(editor);
      textarea.focus();
      textarea.setSelectionRange(0, 0);
      textarea.scrollTop = 0;
      window.requestAnimationFrame?.(() => {
        textarea.scrollTop = 0;
        textarea.setSelectionRange(0, 0);
      });

      const closeEditor = () => {
        editor.remove();
        span.dataset.editing = '0';
        host.classList.remove('inline-editing-host');
        row?.classList.remove('inline-editor-open-row');
        if (activeInlineEditor && activeInlineEditor.taskId === taskId) {
          activeInlineEditor = null;
        }
      };

      activeInlineEditor = { taskId, close: closeEditor };

      cancelBtn.addEventListener('click', () => {
        closeEditor();
      });

      saveBtn.addEventListener('click', async () => {
        const next = textarea.value;

        const resp = await fetch(`/tasks/${taskId}/inline-text`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
          },
          body: JSON.stringify({ text: next }),
        });
        if (!resp.ok) {
          window.alert('Не удалось сохранить');
          return;
        }
        const data = await resp.json();
        span.innerHTML = formatRemarkHtml(data.text ?? next);
        appendTimelineEntry(
          document.querySelector('[data-task-history-list]'),
          document.querySelector('[data-task-history-empty]'),
          data.history_entry,
        );
        closeEditor();
      });
    });
  });

  const remarkSplitStatuses = [
    ['not_started', 'Не выполнено'],
    ['done', 'Выполнено'],
    ['finishers', 'Чистовики'],
    ['contractor', 'Подрядчик'],
    ['guarantee', 'Гарантия'],
  ];

  const trimOuterQuotes = value => {
    const text = String(value || '').trim();
    const quotePairs = { '"': '"', '«': '»', '“': '”', '„': '“', '‹': '›' };
    if (text.length >= 2 && Object.prototype.hasOwnProperty.call(quotePairs, text[0]) && text[text.length - 1] === quotePairs[text[0]]) {
      return text.slice(1, -1).trim();
    }
    return text;
  };

  const compactRemarkText = value => String(value || '')
    .replace(/\s+/g, ' ')
    .replace(/\s+([,.;:!?])/g, '$1')
    .trim();

  const extractQuotedRemarkRanges = text => {
    const pairs = { '"': '"', '«': '»', '“': '”', '„': '“', '‹': '›' };
    const stack = [];
    const ranges = [];
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      if (Object.prototype.hasOwnProperty.call(pairs, char)) {
        if (char === '"' && stack.length && stack[stack.length - 1].close === char) {
          const item = stack.pop();
          if (i > item.start) ranges.push([item.start, i + 1]);
        } else {
          stack.push({ close: pairs[char], start: i });
        }
        continue;
      }
      if (stack.length && char === stack[stack.length - 1].close) {
        const item = stack.pop();
        if (i > item.start) ranges.push([item.start, i + 1]);
      }
    }
    return ranges.sort((a, b) => a[0] - b[0]);
  };

  const buildSplitSuggestion = (text, currentStatus) => {
    const source = String(text || '').trim();
    const ranges = extractQuotedRemarkRanges(source);
    if (!source || !ranges.length) {
      return {
        currentText: source,
        newText: '',
        currentStatus: currentStatus || 'not_started',
        newStatus: 'not_started',
        autoDetected: false,
      };
    }
    let cursor = 0;
    const openParts = [];
    const doneParts = [];
    ranges.forEach(([start, end]) => {
      if (start > cursor) {
        openParts.push(source.slice(cursor, start));
      }
      doneParts.push(trimOuterQuotes(source.slice(start, end)));
      cursor = end;
    });
    if (cursor < source.length) {
      openParts.push(source.slice(cursor));
    }
    const unfinishedText = compactRemarkText(openParts.join(' '));
    const finishedText = compactRemarkText(doneParts.join(' '));
    if (!unfinishedText || !finishedText) {
      return {
        currentText: source,
        newText: '',
        currentStatus: currentStatus || 'not_started',
        newStatus: 'not_started',
        autoDetected: false,
      };
    }
    return {
      currentText: unfinishedText,
      newText: finishedText,
      currentStatus: 'not_started',
      newStatus: 'done',
      autoDetected: true,
    };
  };

  const ensureRemarkSplitModal = () => {
    let modal = document.querySelector('.js-remark-split-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'crm-confirm-overlay js-remark-split-modal d-none';
    modal.innerHTML = `
      <div class="crm-confirm-card remark-split-modal-card" role="dialog" aria-modal="true" aria-labelledby="remark-split-title">
        <div class="remark-split-modal-head">
          <h2 id="remark-split-title">Разделить замечание</h2>
          <button class="remark-split-close js-remark-split-cancel" type="button" aria-label="Закрыть"><i class="bi bi-x-lg"></i></button>
        </div>
        <div class="remark-split-grid">
          <div class="remark-split-pane">
            <label class="form-label">Текущая строка</label>
            <textarea class="form-control js-remark-split-current-text" rows="4"></textarea>
            <select class="form-select js-remark-split-current-status"></select>
          </div>
          <div class="remark-split-pane">
            <label class="form-label">Новая строка</label>
            <textarea class="form-control js-remark-split-new-text" rows="4"></textarea>
            <select class="form-select js-remark-split-new-status"></select>
          </div>
        </div>
        <div class="modal-actions remark-split-actions">
          <button class="btn btn-outline-secondary js-remark-split-cancel" type="button">Отмена</button>
          <button class="btn btn-primary js-remark-split-save" type="button"><i class="bi bi-scissors me-2"></i>Разделить</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    const currentStatus = modal.querySelector('.js-remark-split-current-status');
    const newStatus = modal.querySelector('.js-remark-split-new-status');
    [currentStatus, newStatus].forEach(select => {
      if (!select) return;
      select.innerHTML = remarkSplitStatuses.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join('');
    });
    initDeveloperCustomSelects(modal);
    return modal;
  };

  document.querySelectorAll('.js-split-remark-open').forEach(button => {
    button.addEventListener('click', () => {
      const taskId = button.dataset.taskId;
      const span = document.querySelector(`.inline-text[data-task-id="${taskId}"]`);
      if (!taskId || !span) return;
      const modal = ensureRemarkSplitModal();
      const currentText = modal.querySelector('.js-remark-split-current-text');
      const newText = modal.querySelector('.js-remark-split-new-text');
      const currentStatus = modal.querySelector('.js-remark-split-current-status');
      const newStatus = modal.querySelector('.js-remark-split-new-status');
      const save = modal.querySelector('.js-remark-split-save');
      const suggestion = buildSplitSuggestion(span.textContent || '', button.dataset.taskStatus || 'not_started');

      modal.dataset.taskId = taskId;
      currentText.value = suggestion.currentText || span.textContent || '';
      newText.value = suggestion.newText || '';
      currentStatus.value = suggestion.currentStatus || button.dataset.taskStatus || 'not_started';
      newStatus.value = suggestion.newStatus || 'not_started';
      modal.classList.remove('d-none');
      currentText.scrollTop = 0;
      newText.scrollTop = 0;
      currentText.focus();
      currentText.setSelectionRange(0, 0);
      window.requestAnimationFrame?.(() => {
        currentText.scrollTop = 0;
        newText.scrollTop = 0;
        currentText.setSelectionRange(0, 0);
      });

      const close = () => {
        modal.classList.add('d-none');
        modal.dataset.taskId = '';
      };

      modal.querySelectorAll('.js-remark-split-cancel').forEach(cancel => {
        cancel.onclick = close;
      });
      modal.onclick = event => {
        if (event.target === modal) close();
      };
      save.onclick = async () => {
        const nextCurrent = compactRemarkText(currentText.value);
        const nextNew = compactRemarkText(newText.value);
        if (!nextCurrent || !nextNew) {
          showCrmNotice('Заполните обе части замечания', 'warning');
          return;
        }
        save.disabled = true;
        try {
          const response = await fetch(`/tasks/${taskId}/split`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
              'X-Requested-With': 'XMLHttpRequest',
              'Accept': 'application/json',
            },
            body: JSON.stringify({
              current_text: nextCurrent,
              new_text: nextNew,
              current_status: currentStatus.value || 'not_started',
              new_status: newStatus.value || 'not_started',
            }),
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok || data.ok === false) {
            throw new Error(data.message || 'Не удалось разделить замечание');
          }
          close();
          showCrmNotice(data.message || 'Замечание разделено', 'success');
          window.setTimeout(() => window.location.reload(), 220);
        } catch (error) {
          showCrmNotice(error.message || 'Не удалось разделить замечание', 'danger');
        } finally {
          save.disabled = false;
        }
      };
    });
  });

  document.querySelectorAll('.object-card[data-href]').forEach(card => {
    const openCard = event => {
      if (event.target.closest('a, button, form')) return;
      navigateWithViewportTransition(card.dataset.href);
    };
    card.addEventListener('click', openCard);
    card.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openCard(event);
      }
    });
  });


  const bindTaskRowLink = row => {
    if (!row || row.dataset.rowLinkBound === '1') return;
    row.dataset.rowLinkBound = '1';
    const openRow = event => {
      if (event.target.closest('a, button, form, input, textarea, select, label, .inline-editor, .problem-comment-wrap')) return;
      const bulkScope = row.closest('.js-bulk-selectable');
      if (bulkScope?.dataset.bulkRowDblclick) return;
      navigateWithViewportTransition(row.dataset.href);
    };
    const openEvent = row.dataset.openOnClick ? 'click' : 'dblclick';
    row.addEventListener(openEvent, openRow);
  };
  document.querySelectorAll('.task-row-link[data-href]').forEach(bindTaskRowLink);

  document.querySelectorAll('.related-task-item[data-href]').forEach(item => {
    item.addEventListener('click', event => {
      if (event.target.closest('a, button, form, input, textarea, select, label, .inline-editor')) return;
      navigateWithViewportTransition(item.dataset.href);
    });
    item.setAttribute('tabindex', '0');
    item.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        navigateWithViewportTransition(item.dataset.href);
      }
    });
  });

  document.querySelectorAll('.apartment-card').forEach(card => {
    card.addEventListener('click', event => {
      if (event.target.closest('a, button, form, input, textarea, select, label')) return;
      const href = card.querySelector('.apartment-card-link')?.getAttribute('href');
      if (href) {
        navigateWithViewportTransition(href);
      }
    });
  });

  const appendTimelineEntry = (list, emptyNode, entry) => {
    if (!list || !entry) return;
    const item = document.createElement('div');
    item.className = 'timeline-item';
    const meta = document.createElement('div');
    meta.className = 'small text-muted';
    meta.textContent = [entry.timestamp, entry.actor, entry.point_label].filter(Boolean).join(' · ');
    const summary = document.createElement('div');
    summary.textContent = entry.summary || '';
    if (entry.summary_class) summary.className = entry.summary_class;
    item.append(meta, summary);
    list.prepend(item);
    list.hidden = false;
    if (emptyNode) emptyNode.hidden = true;
  };

  const syncBinaryStatusToggle = (form, isDone) => {
    if (!form?.matches?.('[data-binary-status-toggle]')) return;
    const done = Boolean(isDone);
    const button = form.querySelector('[data-binary-status-toggle-button]');
    const icon = form.querySelector('[data-binary-status-toggle-icon]');
    const labelNode = form.querySelector('[data-binary-status-toggle-label]');
    const label = done
      ? (form.dataset.notDoneLabel || 'Не выполнено')
      : (form.dataset.doneLabel || 'Выполнено');

    form.action = done
      ? (form.dataset.notStartedUrl || form.action)
      : (form.dataset.doneUrl || form.action);
    form.dataset.statusAction = done ? 'not_started' : 'done';
    form.dataset.isDone = done ? '1' : '0';
    form.classList.remove('d-none');

    if (button) {
      button.classList.toggle('btn-outline-success', !done);
      button.classList.toggle('btn-outline-secondary', done);
      button.title = label;
      button.setAttribute('aria-label', label);
    }
    if (icon) {
      icon.classList.toggle('bi-check2-circle', !done);
      icon.classList.toggle('bi-arrow-counterclockwise', done);
    }
    if (labelNode) labelNode.textContent = label;
  };

  document.querySelectorAll('[data-binary-status-toggle]').forEach(form => {
    syncBinaryStatusToggle(form, form.dataset.isDone === '1');
  });

  const syncStatusActionVisibility = (root = document) => {
    const returnableStatuses = new Set(['done', 'finishers', 'contractor', 'guarantee', 'concession']);
    root.querySelectorAll('.actions-cell[data-current-status]').forEach(actionsCell => {
      const currentStatus = actionsCell.dataset.currentStatus || '';
      actionsCell.querySelectorAll('.status-action-form[data-status-action]').forEach(actionForm => {
        if (actionForm.matches('[data-binary-status-toggle]')) {
          // Из любого завершающего статуса возвращаем замечание в «Не выполнено».
          syncBinaryStatusToggle(actionForm, returnableStatuses.has(currentStatus));
          actionForm.classList.remove('d-none');
          return;
        }
        const action = actionForm.dataset.statusAction || '';
        let shouldHide = action === currentStatus;
        if (action === 'done') shouldHide = currentStatus !== 'not_started';
        if (action === 'not_started') shouldHide = currentStatus !== 'done';
        actionForm.classList.toggle('d-none', shouldHide);
      });
    });
  };

  const syncApartmentLiveStats = (serverStats = null) => {
    const stats = document.querySelector('[data-apartment-live-stats]');
    if (!stats) return;
    const hasServerStats = serverStats && typeof serverStats === 'object';
    const items = hasServerStats ? [] : Array.from(document.querySelectorAll('.apartment-task-list .apartment-task-item'));
    const total = hasServerStats ? Number(serverStats.total || 0) : items.length;
    const done = hasServerStats ? Number(serverStats.done || 0) : items.filter(item => item.classList.contains('is-done')).length;
    const problem = hasServerStats
      ? Number(serverStats.problem || 0)
      : items.filter(item => {
          if (item.dataset.taskStatus) return item.dataset.taskStatus === 'problem';
          return Array.from(item.querySelectorAll('.actions-cell[data-current-status]')).some(cell => cell.dataset.currentStatus === 'problem');
        }).length;
    const left = hasServerStats ? Number(serverStats.left || 0) : Math.max(total - done, 0);
    const percent = hasServerStats ? Number(serverStats.percent || 0) : (total ? Math.round((done / total) * 1000) / 10 : 0);
    const percentText = `${percent.toFixed(1)}%`;
    const setText = (selector, value) => {
      const node = stats.querySelector(selector);
      if (node) node.textContent = value;
    };

    setText('[data-apartment-stat-percent]', percentText);
    setText('[data-apartment-stat-total]', total);
    setText('[data-apartment-stat-done]', done);
    setText('[data-apartment-stat-left]', left);
    setText('[data-apartment-stat-problem]', problem);

    const progress = stats.querySelector('[data-apartment-stat-progress]');
    if (progress) {
      progress.style.width = percentText;
      progress.setAttribute('aria-valuenow', String(percent));
    }
  };

  syncStatusActionVisibility();
  syncApartmentLiveStats();

  const chooseGuaranteeContractor = contractors => new Promise(resolve => {
    const modalElement = document.getElementById('guaranteeContractorModal');
    const options = modalElement?.querySelector('[data-guarantee-contractor-options]');
    if (!modalElement || !options || !window.bootstrap?.Modal || !Array.isArray(contractors)) {
      resolve(null);
      return;
    }

    options.replaceChildren();
    let selectedContractorId = null;
    contractors.forEach(contractor => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'guarantee-contractor-option';
      const icon = document.createElement('span');
      icon.className = 'guarantee-contractor-option-icon';
      icon.innerHTML = '<i class="bi bi-person-gear" aria-hidden="true"></i>';
      const name = document.createElement('strong');
      name.textContent = contractor.name || `Подрядчик ${contractor.id}`;
      const arrow = document.createElement('i');
      arrow.className = 'bi bi-chevron-right guarantee-contractor-option-arrow';
      arrow.setAttribute('aria-hidden', 'true');
      button.append(icon, name, arrow);
      button.addEventListener('click', () => {
        selectedContractorId = String(contractor.id);
        modal.hide();
      });
      options.append(button);
    });

    const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
    modalElement.addEventListener('hidden.bs.modal', () => {
      resolve(selectedContractorId);
    }, { once: true });
    modal.show();
  });

  document.querySelectorAll('form[action*="/status/"]').forEach(form => {
    form.addEventListener('click', event => {
      event.stopPropagation();
    });
    form.addEventListener('submit', async event => {
      const row = form.closest('.task-row-link, [data-task-detail-shell]');
      const isTaskDetail = form.dataset.taskDetailStatus === '1';
      if (!row && !isTaskDetail) return;
      if (!form.checkValidity()) {
        return;
      }
      event.preventDefault();

      const submitBtn = event.submitter || form.querySelector('button[type="submit"], button:not([type])');
      if (submitBtn) submitBtn.disabled = true;

      try {
        const formData = new FormData(form);
        const needsDesktopContractorChoice = document.documentElement.classList.contains('desktop-like-pointer')
          && form.dataset.statusAction === 'guarantee';
        if (needsDesktopContractorChoice) {
          formData.set('require_contractor_choice', '1');
          if (form.dataset.guaranteeChoiceReady === '1') {
            delete form.dataset.guaranteeChoiceReady;
          } else {
            formData.delete('guarantee_contractor_id');
          }
        }
        const resp = await fetch(form.action, {
          method: 'POST',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
          },
          body: formData,
        });
        const data = await resp.json().catch(() => null);
        if (resp.status === 409 && data?.requires_contractor_choice) {
          const contractorId = await chooseGuaranteeContractor(data.contractors || []);
          if (contractorId) {
            let selectedInput = form.querySelector('input[name="guarantee_contractor_id"]');
            if (!selectedInput) {
              selectedInput = document.createElement('input');
              selectedInput.type = 'hidden';
              selectedInput.name = 'guarantee_contractor_id';
              form.append(selectedInput);
            }
            selectedInput.value = contractorId;
            form.dataset.guaranteeChoiceReady = '1';
            window.setTimeout(() => form.requestSubmit(submitBtn || undefined), 0);
          }
          return;
        }
        if (!resp.ok) {
          if (!data || !data.message) {
            HTMLFormElement.prototype.submit.call(form);
            return;
          }
          window.alert(data.message || 'Не удалось изменить статус');
          return;
        }
        if (!data || data.ok === false) {
          if (!data) {
            HTMLFormElement.prototype.submit.call(form);
            return;
          }
          window.alert(data.message || 'Не удалось изменить статус');
          return;
        }

        const badge = row?.querySelector('[data-status-pill]') || row?.querySelector('.task-status-cell .badge') || row?.querySelector('td .badge');
        if (badge) {
          const isBinaryDoneStatus = badge.dataset.binaryDoneStatus === '1';
          if (badge.classList.contains('status-pill')) {
            const apartmentToggleClass = badge.classList.contains('apartment-task-status-btn') ? ' apartment-task-status-btn' : '';
            const contractorToggleClass = badge.classList.contains('contractor-task-status-btn') ? ' contractor-task-status-btn' : '';
            if (isBinaryDoneStatus) {
              badge.className = `status-pill ${data.is_done ? 'status-pill-success' : 'status-pill-muted'}${apartmentToggleClass}${contractorToggleClass}`;
            } else {
              const pillClassMap = {
                success: 'status-pill-success',
                info: 'status-pill-info',
                warning: 'status-pill-warning',
                primary: 'status-pill-primary',
                danger: 'status-pill-danger',
                secondary: 'status-pill-muted'
              };
              badge.className = `status-pill ${pillClassMap[data.status_class] || 'status-pill-muted'}${apartmentToggleClass}${contractorToggleClass}`;
            }
          } else {
            badge.className = `badge bg-${data.status_class || 'secondary'}`;
          }
          if (isBinaryDoneStatus) {
            badge.textContent = data.is_done ? (badge.dataset.doneLabel || 'Выполнено') : (badge.dataset.notDoneLabel || 'Не выполнено');
          } else {
            badge.textContent = data.status_label || data.status || '';
          }
        }
        row?.classList.toggle('table-success', Boolean(data.is_done));
        row?.classList.toggle('done-task', Boolean(data.is_done));
        row?.classList.toggle('is-done', Boolean(data.is_done));
        if (row) moveDoneItemToBottom(row);
        if (isTaskDetail) {
          document.querySelector('.task-text')?.classList.toggle('text-decoration-line-through', Boolean(data.is_done));
          appendTimelineEntry(
            document.querySelector('[data-task-history-list]'),
            document.querySelector('[data-task-history-empty]'),
            data.history_entry,
          );
        }

        if (form.dataset.reloadAfterStatus === '1') {
          // Не обновляем страницу сразу: пользователь должен видеть строку/карточку на месте
          // и иметь возможность быстро вернуть действие обратно.
        }

        const binaryToggleRoot = row || document;
        if (binaryToggleRoot.matches?.('[data-binary-status-toggle]')) {
          syncBinaryStatusToggle(binaryToggleRoot, Boolean(data.is_done));
        }
        binaryToggleRoot.querySelectorAll?.('[data-binary-status-toggle]').forEach(toggleForm => {
          syncBinaryStatusToggle(toggleForm, Boolean(data.is_done));
        });

        const actionCells = [];
        if (row?.matches?.('.actions-cell')) actionCells.push(row);
        row?.querySelectorAll?.('.actions-cell').forEach(cell => actionCells.push(cell));
        actionCells.forEach(cell => {
          cell.dataset.currentStatus = data.status || '';
        });
        if (row?.classList.contains('apartment-task-item')) {
          row.dataset.taskStatus = data.status || '';
        }
        syncStatusActionVisibility(row || document);
        syncApartmentLiveStats(data.apartment_stats);

        const submittedProblemInput = form.querySelector('input[name="problem_comment"]');
        if (submittedProblemInput) submittedProblemInput.remove();

        const problemWrap = form.querySelector('.problem-comment-wrap');
        const problemToggle = form.querySelector('.problem-toggle-btn');
        const problemInput = form.querySelector('input[name="problem_comment"]');
        if (problemWrap && problemToggle && problemInput) {
          problemInput.value = '';
          problemWrap.classList.add('d-none');
          form.classList.remove('problem-popover-open');
          problemWrap.removeAttribute('style');
          problemToggle.classList.remove('d-none');
          problemToggle.classList.remove('problem-toggle-open');
        }
      } catch (error) {
        HTMLFormElement.prototype.submit.call(form);
        return;
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  });

  document.querySelectorAll('form[data-apartment-async="1"]').forEach(form => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!form.checkValidity()) return;

      const submitter = event.submitter || form.querySelector('button[type="submit"], button:not([type])');
      const previousHtml = submitter?.innerHTML || '';
      if (submitter) submitter.disabled = true;

      try {
        const formData = new FormData(form);
        if (submitter?.name) {
          formData.set(submitter.name, submitter.value ?? '');
        }
        const response = await fetch(form.action, {
          method: 'POST',
          body: formData,
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) {
          throw new Error(data.message || 'Не удалось сохранить изменения');
        }

        const inspectionDisplay = document.querySelector('[data-apartment-inspection-display]');
        if (inspectionDisplay && Object.prototype.hasOwnProperty.call(data, 'inspection_date_label')) {
          const status = escapeHtml(data.inspection_status || '');
          const statusClass = escapeHtml(data.inspection_status_class || 'status-pill-muted');
          const label = escapeHtml(data.inspection_date_label || '—');
          inspectionDisplay.innerHTML = status
            ? `<span class="status-pill ${statusClass}">${status}</span><span>${label}</span>`
            : label;
        }

        const commentDisplay = document.querySelector('[data-apartment-comment-display]');
        if (commentDisplay && Object.prototype.hasOwnProperty.call(data, 'comment')) {
          commentDisplay.textContent = data.comment || '—';
        }

        const inspectionNoteDisplay = document.querySelector('[data-apartment-inspection-note-display]');
        if (inspectionNoteDisplay && Object.prototype.hasOwnProperty.call(data, 'inspection_note')) {
          inspectionNoteDisplay.textContent = data.inspection_note || '—';
        }

        const avrDisplay = document.querySelector('[data-apartment-avr-display]');
        if (avrDisplay && Object.prototype.hasOwnProperty.call(data, 'avr_status')) {
          avrDisplay.innerHTML = data.avr_status === 'signed'
            ? `<span class="badge-avr-signed">Подписан${data.avr_signed_date_label ? ` от ${escapeHtml(data.avr_signed_date_label)}` : ''}</span>`
            : '<span class="badge-avr-needed">Нужен</span>';
        }
        if (form.classList.contains('apartment-avr-form') && Object.prototype.hasOwnProperty.call(data, 'avr_status')) {
          form.querySelectorAll('button[name="avr_status"]').forEach(statusButton => {
            const isActive = statusButton.value === data.avr_status;
            statusButton.classList.remove('btn-primary', 'btn-outline-primary', 'btn-success', 'btn-outline-success');
            if (statusButton.value === 'signed') {
              statusButton.classList.add(isActive ? 'btn-success' : 'btn-outline-success');
            } else {
              statusButton.classList.add(isActive ? 'btn-primary' : 'btn-outline-primary');
            }
          });
          const signedDateInput = form.querySelector('input[name="avr_signed_date"]');
          if (signedDateInput && data.avr_signed_date) signedDateInput.value = data.avr_signed_date;
        }

        if (data.history_entry) {
          const historyList = document.querySelector('[data-apartment-history-list]');
          const historyEmpty = document.querySelector('[data-apartment-history-empty]');
          if (historyList && String(historyList.dataset.currentPage || '1') === '1') {
            const item = document.createElement('div');
            item.className = 'timeline-item';
            const meta = document.createElement('div');
            meta.className = 'small text-muted';
            meta.textContent = [
              data.history_entry.timestamp,
              data.history_entry.actor,
              data.history_entry.point_label,
            ].filter(Boolean).join(' · ');
            const summary = document.createElement('div');
            summary.textContent = data.history_entry.summary || '';
            if (data.history_entry.summary_class) summary.className = data.history_entry.summary_class;
            item.append(meta, summary);
            historyList.prepend(item);
            historyList.hidden = false;
            if (historyEmpty) historyEmpty.hidden = true;
          }
        }

        showCrmNotice(data.message || 'Сохранено', 'success');
      } catch (error) {
        showCrmNotice(error.message || 'Не удалось сохранить изменения', 'danger');
      } finally {
        if (submitter) {
          submitter.disabled = false;
          submitter.innerHTML = previousHtml;
        }
      }
    });
  });

  document.querySelectorAll('.password-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const field = btn.closest('.password-field')?.querySelector('input');
      const icon = btn.querySelector('i');
      if (!field) return;
      const show = field.type === 'password';
      field.type = show ? 'text' : 'password';
      if (icon) icon.className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
    });
  });

  document.querySelectorAll('.password-preview-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const wrapper = btn.closest('.password-preview');
      const text = wrapper?.querySelector('span');
      const icon = btn.querySelector('i');
      if (!wrapper || !text) return;
      const show = wrapper.dataset.state !== 'visible';
      wrapper.dataset.state = show ? 'visible' : 'hidden';
      text.textContent = show ? wrapper.dataset.visible : wrapper.dataset.hidden;
      if (icon) icon.className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
    });
  });

  document.querySelectorAll('.users-captcha-form').forEach(form => {
    const input = form.querySelector('.users-captcha-input');
    const valueField = form.querySelector('[data-captcha-disabled-value]');
    const status = form.querySelector('.users-captcha-toggle small');
    if (!input || !valueField) return;

    let savedChecked = input.checked;
    const syncView = checked => {
      input.checked = checked;
      valueField.value = checked ? '0' : '1';
      if (status) status.textContent = checked ? 'Вкл.' : 'Откл.';
    };

    input.addEventListener('change', async () => {
      const requestedChecked = input.checked;
      syncView(requestedChecked);
      input.disabled = true;
      form.classList.add('is-saving');

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) {
          throw new Error(data.message || 'Не удалось сохранить настройку капчи');
        }

        savedChecked = data.captcha_disabled === undefined
          ? requestedChecked
          : !data.captcha_disabled;
        syncView(savedChecked);
        showCrmNotice(data.message || 'Настройка капчи сохранена.', 'success');
      } catch (error) {
        syncView(savedChecked);
        showCrmNotice(error.message || 'Не удалось сохранить настройку капчи', 'danger');
      } finally {
        input.disabled = false;
        form.classList.remove('is-saving');
      }
    });
  });

  const problemModalEl = document.getElementById('taskProblemModal');
  const problemModalForm = document.getElementById('taskProblemModalForm');
  const problemModalComment = document.getElementById('taskProblemModalComment');
  const problemModalTitle = problemModalEl?.querySelector('.modal-title');
  let activeProblemForm = null;

  const resetProblemModal = () => {
    if (problemModalComment) problemModalComment.value = '';
    problemModalForm?.classList.remove('was-validated');
    activeProblemForm = null;
  };

  const setProblemCommentField = (form, value) => {
    let hidden = form.querySelector('input[name="problem_comment"]');
    if (!hidden) {
      hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'problem_comment';
      form.appendChild(hidden);
    }
    hidden.value = value;
  };

  const openProblemModal = (form, title) => {
    if (!form || !problemModalEl || !problemModalForm || !problemModalComment) return;
    activeProblemForm = form;
    problemModalForm.classList.remove('was-validated');
    problemModalComment.value = '';
    if (problemModalTitle) problemModalTitle.textContent = title || 'Проблема';
    if (window.bootstrap?.Modal) {
      const modal = bootstrap.Modal.getOrCreateInstance(problemModalEl);
      modal.show();
      problemModalEl.addEventListener('shown.bs.modal', () => {
        problemModalComment.focus();
      }, { once: true });
    } else {
      const fallback = window.prompt('');
      if (fallback && fallback.trim()) {
        setProblemCommentField(form, fallback.trim());
        form.requestSubmit ? form.requestSubmit() : form.submit();
      }
    }
  };

  document.querySelectorAll('.problem-toggle-btn').forEach(btn => {
    btn.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      const form = btn.closest('.problem-action-form');
      openProblemModal(form, btn.dataset.problemModalTitle || btn.getAttribute('title') || 'Проблема');
    });
  });

  problemModalForm?.addEventListener('submit', event => {
    event.preventDefault();
    if (!activeProblemForm || !problemModalComment) return;
    const value = problemModalComment.value.trim();
    if (!value) {
      problemModalForm.classList.add('was-validated');
      problemModalComment.focus();
      return;
    }
    setProblemCommentField(activeProblemForm, value);
    if (window.bootstrap?.Modal && problemModalEl) {
      bootstrap.Modal.getOrCreateInstance(problemModalEl).hide();
    }
    activeProblemForm.requestSubmit ? activeProblemForm.requestSubmit() : activeProblemForm.submit();
  });

  problemModalEl?.addEventListener('hidden.bs.modal', resetProblemModal);

  const fillMaterialRow = (row, name, unit) => {
    if (!row) return;
    const nameInput = row.querySelector('input[name="name[]"]');
    const unitInput = row.querySelector('input[name="unit[]"]');
    if (nameInput) nameInput.value = name;
    if (unitInput && (!unitInput.value || unitInput.value.trim() === '')) unitInput.value = unit;
    const qtyInput = row.querySelector('input[name="quantity[]"]');
    if (qtyInput && (!qtyInput.value || qtyInput.value.trim() === '')) qtyInput.focus();
  };

  document.querySelectorAll('.material-preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const table = btn.closest('form')?.querySelector('.material-edit-table');
      if (!table) return;
      const rows = Array.from(table.querySelectorAll('tbody tr'));
      const emptyRow = rows.find(row => {
        const nameInput = row.querySelector('input[name="name[]"]');
        return nameInput && !nameInput.value.trim();
      }) || rows[0];
      fillMaterialRow(emptyRow, btn.dataset.name || '', btn.dataset.unit || '');
    });
  });

  const presetUnits = {
    'ротбанд': 'меш',
    'плитонит b': 'меш',
    'ветонит (lr)': 'меш',
    'ветонит (kr)': 'меш',
    'наливной пол': 'меш',
    'стеклопакет': 'шт',
    'стекло': 'шт',
    'рама': 'шт',
  };

  document.querySelectorAll('.material-name-input').forEach(input => {
    input.addEventListener('change', () => {
      const row = input.closest('tr');
      const unitInput = row?.querySelector('.material-unit-input');
      if (!unitInput || unitInput.value.trim()) return;
      const key = input.value.trim().toLowerCase();
      if (presetUnits[key]) unitInput.value = presetUnits[key];
    });
  });

  document.querySelectorAll('.js-material-request-add-row').forEach(btn => {
    btn.addEventListener('click', () => {
      const form = btn.closest('form');
      const tbody = form?.querySelector('.material-edit-table tbody');
      const lastRow = tbody?.querySelector('tr:last-child');
      if (!tbody || !lastRow) return;
      const maxRows = Number(tbody.dataset.maxRows || 10);
      if (tbody.querySelectorAll('tr').length >= maxRows) {
        btn.disabled = true;
        return;
      }
      const clone = lastRow.cloneNode(true);
      clone.querySelectorAll('input').forEach(input => {
        input.value = '';
        input.classList.remove('is-invalid');
      });
      const numberCell = clone.querySelector('td:first-child');
      if (numberCell) numberCell.textContent = String(tbody.querySelectorAll('tr').length + 1);
      tbody.appendChild(clone);
      const nameInput = clone.querySelector('.material-name-input');
      if (nameInput) {
        nameInput.addEventListener('change', () => {
          const unitInput = clone.querySelector('.material-unit-input');
          if (!unitInput || unitInput.value.trim()) return;
          const key = nameInput.value.trim().toLowerCase();
          if (presetUnits[key]) unitInput.value = presetUnits[key];
        });
        nameInput.focus();
      }
      if (tbody.querySelectorAll('tr').length >= maxRows) {
        btn.disabled = true;
      }
    });
  });

  document.querySelectorAll('.js-material-writeoff-add-row').forEach(btn => {
    if (!document.documentElement.classList.contains('desktop-like-pointer')) return;
    const form = btn.closest('.js-material-writeoff-edit-form');
    const tbody = form?.querySelector('.material-edit-table tbody');
    if (!tbody) return;

    const bindMaterialUnitPreset = row => {
      const nameInput = row.querySelector('.material-name-input');
      if (!nameInput || nameInput.dataset.unitPresetBound === '1') return;
      nameInput.dataset.unitPresetBound = '1';
      nameInput.addEventListener('change', () => {
        const unitInput = row.querySelector('.material-unit-input');
        if (!unitInput || unitInput.value.trim()) return;
        const key = nameInput.value.trim().toLowerCase();
        if (presetUnits[key]) unitInput.value = presetUnits[key];
      });
    };

    const updateButtonState = () => {
      btn.disabled = tbody.querySelectorAll('tr:not(.material-writeoff-empty-row)').length >= 20;
    };

    btn.addEventListener('click', () => {
      if (tbody.querySelectorAll('tr:not(.material-writeoff-empty-row)').length >= 20) {
        updateButtonState();
        return;
      }
      let row = tbody.querySelector('.material-writeoff-empty-row');
      if (row) {
        row.classList.remove('material-writeoff-empty-row');
      } else {
        const rows = tbody.querySelectorAll('tr');
        const sourceRow = rows[rows.length - 1];
        if (!sourceRow || rows.length >= 20) {
          updateButtonState();
          return;
        }
        row = sourceRow.cloneNode(true);
        row.querySelectorAll('input').forEach(input => {
          input.value = '';
          input.classList.remove('is-invalid');
          delete input.dataset.unitPresetBound;
        });
        const numberCell = row.querySelector('td:first-child');
        if (numberCell) numberCell.textContent = String(rows.length + 1);
        tbody.appendChild(row);
      }
      bindMaterialUnitPreset(row);
      row.querySelector('.material-name-input')?.focus();
      updateButtonState();
    });

    updateButtonState();
  });

  document.querySelectorAll('.js-material-request-form').forEach(form => {
    const rowFields = row => ({
      name: row.querySelector('input[name="name[]"]'),
      quantity: row.querySelector('input[name="quantity[]"]'),
      unit: row.querySelector('input[name="unit[]"]'),
    });
    const hasValue = field => Boolean(field?.value.trim());
    const validQuantity = field => {
      const value = Number((field?.value || '').trim().replace(',', '.'));
      return Number.isFinite(value) && value > 0;
    };

    form.addEventListener('input', event => {
      const field = event.target.closest('input[name="name[]"], input[name="quantity[]"], input[name="unit[]"]');
      if (!field) return;
      const valid = field.name === 'quantity[]' ? validQuantity(field) : hasValue(field);
      if (valid) field.classList.remove('is-invalid');
    });

    form.addEventListener('submit', event => {
      const rows = Array.from(form.querySelectorAll('.material-edit-table tbody tr'));
      const activeRows = rows.filter(row => Object.values(rowFields(row)).some(hasValue));
      const rowsToValidate = activeRows.length ? activeRows : rows.slice(0, 1);
      const invalid = [];

      rowsToValidate.forEach(row => {
        const fields = rowFields(row);
        if (!hasValue(fields.name)) invalid.push(fields.name);
        if (!validQuantity(fields.quantity)) invalid.push(fields.quantity);
        if (!hasValue(fields.unit)) invalid.push(fields.unit);
      });
      invalid.filter(Boolean).forEach(field => field.classList.add('is-invalid'));
      if (!invalid.length) return;

      event.preventDefault();
      event.stopImmediatePropagation();
      const firstInvalid = invalid.find(Boolean);
      firstInvalid?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      window.setTimeout(() => firstInvalid?.focus({ preventScroll: true }), 180);
    });
  });

  document.querySelectorAll('.js-material-request-edit').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelector('.js-material-request-view')?.classList.add('d-none');
      document.querySelector('.js-material-request-edit-form')?.classList.remove('d-none');
      btn.classList.add('d-none');
      document.querySelector('.js-material-request-edit-form input[name="title"]')?.focus();
    });
  });

  document.querySelectorAll('.js-material-request-cancel').forEach(btn => {
    btn.addEventListener('click', () => {
      const form = btn.closest('.js-material-request-edit-form');
      form?.classList.add('d-none');
      document.querySelector('.js-material-request-view')?.classList.remove('d-none');
      document.querySelector('.js-material-request-edit')?.classList.remove('d-none');
      if (form) form.reset();
    });
  });

});

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.js-check-all').forEach(btn => {
    btn.addEventListener('click', () => {
      const selector = btn.dataset.target;
      if (!selector) return;
      const scope = btn.closest('.js-bulk-selectable') || document;
      const checks = Array.from(scope.querySelectorAll(selector)).filter(el => !el.disabled && !el.closest('.js-bulk-row[hidden]'));
      const shouldCheck = checks.some(el => !el.checked);
      checks.forEach(el => {
        el.checked = shouldCheck;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      });
      btn.textContent = shouldCheck ? 'Снять выбор' : 'Выбрать все';
    });
  });
});

document.addEventListener('DOMContentLoaded', () => {
  const pluralLabel = (count, scope) => {
    const one = scope.dataset.bulkLabelOne || 'заявка';
    const few = scope.dataset.bulkLabelFew || 'заявки';
    const many = scope.dataset.bulkLabelMany || 'заявок';
    const mod10 = count % 10;
    const mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
  };
  const bulkStorageKey = (scope) => {
    if (scope.dataset.noPersistSelection === '1') return '';
    if (scope.dataset.selectionKey) return `crm-bulk-selection:${scope.dataset.selectionKey}`;
    const scopes = Array.from(document.querySelectorAll('.js-bulk-selectable'));
    const scopeIndex = Math.max(scopes.indexOf(scope), 0);
    const params = new URLSearchParams(window.location.search || '');
    params.delete('page');
    const normalizedQuery = params.toString();
    return `crm-bulk-selection:auto:${window.location.pathname}:${normalizedQuery}:scope-${scopeIndex}`;
  };
  const bulkStorage = (scope) => scope.dataset.selectionStorage === 'session' ? window.sessionStorage : window.localStorage;
  const removeStorageKey = (storage, key) => {
    try { storage.removeItem(key); } catch (error) {}
  };
  const clearStorageByPrefix = (storage, prefix) => {
    try {
      for (let index = storage.length - 1; index >= 0; index -= 1) {
        const key = storage.key(index);
        if (key && key.startsWith(prefix)) storage.removeItem(key);
      }
    } catch (error) {}
  };
  const clearAllBulkSelectionStorage = () => {
    clearStorageByPrefix(window.sessionStorage, 'crm-bulk-selection:');
    clearStorageByPrefix(window.localStorage, 'crm-bulk-selection:');
  };
  const shouldClearBulkSelectionOnLink = (link, url) => {
    if (url.origin !== window.location.origin) return false;
    if (link.dataset.preserveBulkSelection === '1') return false;
    if (link.closest('.pagination') || isPaginationNavigation(url)) return false;
    if (link.closest('.task-row-link, .related-task-item, .apartment-card, .object-card')) return false;
    if (link.classList.contains('task-detail-back-btn')) return false;
    if (link.closest('.sidebar-link, .sidebar-sublink, .crm-tabs, .developer-section-tabs, .site-errors-kind-tabs, .remarks-tabs, .nav')) return true;
    return url.pathname !== window.location.pathname;
  };
  window.clearCrmBulkSelectionStorage = clearAllBulkSelectionStorage;
  const clearBulkSelectionForScope = (scope, { resetUi = true } = {}) => {
    const key = bulkStorageKey(scope);
    if (key) removeStorageKey(bulkStorage(scope), key);
    if (!(scope.__bulkSelectedIds instanceof Set)) return;
    scope.__bulkSelectedIds.clear();
    if (!resetUi) return;
    scope.querySelectorAll('.js-bulk-check').forEach(check => { check.checked = false; });
    syncBulkScope(scope);
  };
  const readBulkSelection = (scope) => {
    const key = bulkStorageKey(scope);
    if (!key) return null;
    const storage = bulkStorage(scope);
    const stored = storage.getItem(key);
    if (stored === null) return null;
    try {
      const values = JSON.parse(stored || '[]');
      return new Set(Array.isArray(values) ? values.map(String) : []);
    } catch (error) {
      return new Set();
    }
  };
  const writeBulkSelection = (scope) => {
    const key = bulkStorageKey(scope);
    if (!key || !(scope.__bulkSelectedIds instanceof Set)) return;
    const storage = bulkStorage(scope);
    storage.setItem(key, JSON.stringify(Array.from(scope.__bulkSelectedIds)));
  };
  const syncBulkExportForm = (scope) => {
    const selector = scope.dataset.exportForm;
    if (!selector || !(scope.__bulkSelectedIds instanceof Set)) return;
    const form = document.querySelector(selector);
    if (!form) return;
    form.querySelectorAll('input[name="task_ids"]').forEach(input => input.remove());
    const hasHiddenPremises = Array.from(scope.querySelectorAll('.js-premise-visibility')).some(input => !input.checked);
    const ids = scope.__bulkSelectedIds.size
      ? Array.from(scope.__bulkSelectedIds)
      : (hasHiddenPremises
        ? Array.from(scope.querySelectorAll('.js-bulk-row:not([hidden]) .js-bulk-check')).map(check => String(check.value || '')).filter(Boolean)
        : []);
    ids.forEach(taskId => {
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'task_ids';
      input.value = taskId;
      form.appendChild(input);
    });
  };
  const syncBulkPersistedInputs = (scope) => {
    if (!(scope?.__bulkSelectedIds instanceof Set)) return;
    const form = scope instanceof HTMLFormElement
      ? scope
      : (scope.dataset.bulkPersistForm ? document.querySelector(scope.dataset.bulkPersistForm) : null);
    if (!(form instanceof HTMLFormElement)) return;
    const inputName = scope.dataset.bulkPersistName || 'task_ids';
    form.querySelectorAll('input.js-bulk-persisted-input').forEach(input => input.remove());
    const visibleCheckIds = new Set(
      Array.from(scope.querySelectorAll('.js-bulk-check')).map(check => String(check.value || '')).filter(Boolean)
    );
    Array.from(scope.__bulkSelectedIds).forEach(selectedId => {
      if (visibleCheckIds.has(String(selectedId))) return;
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = inputName;
      input.value = selectedId;
      input.className = 'js-bulk-persisted-input';
      form.appendChild(input);
    });
  };
  const isBulkCheckAvailable = (check) => !check.disabled && !check.closest('.js-bulk-row[hidden]');

  const isPaginationNavigation = (url) => {
    if (url.origin !== window.location.origin || url.pathname !== window.location.pathname) return false;
    const currentParams = new URLSearchParams(window.location.search || '');
    const nextParams = new URLSearchParams(url.search || '');
    const currentPage = currentParams.get('page') || '';
    const nextPage = nextParams.get('page') || '';
    currentParams.delete('page');
    nextParams.delete('page');
    return currentPage !== nextPage && currentParams.toString() === nextParams.toString();
  };

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const method = (form.getAttribute('method') || 'get').toLowerCase();
    if (method === 'get' && form.matches('.crm-filter-form, .apartments-filter-form, .assignment-search-form, .assignment-smart-form, .assignment-report-filter-form')) {
      clearAllBulkSelectionStorage();
      return;
    }
    const scope = form.closest('.js-bulk-selectable') || document.querySelector(`.js-bulk-selectable button[form="${form.id}"]`)?.closest('.js-bulk-selectable');
    if (scope && (form.id || form.querySelector('[name="measurement_ids"], [name="task_ids"]'))) {
      clearBulkSelectionForScope(scope, { resetUi: false });
    }
  }, true);

  document.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.target || link.hasAttribute('download')) return;
    const href = link.getAttribute('href') || '';
    if (!href || href === '#' || href.startsWith('#')) return;
    try {
      const url = new URL(href, window.location.href);
      if (shouldClearBulkSelectionOnLink(link, url)) clearAllBulkSelectionStorage();
    } catch (error) {}
  }, true);

  const syncBulkScope = (scope) => {
    const checks = Array.from(scope.querySelectorAll('.js-bulk-check')).filter(isBulkCheckAvailable);
    const selected = checks.filter(check => check.checked);
    const visibleSelectedCount = selected.length;
    const persisted = scope.__bulkSelectedIds instanceof Set ? scope.__bulkSelectedIds : null;
    const selectedCount = persisted ? persisted.size : selected.length;
    const label = pluralLabel(selectedCount, scope);
    const panel = scope.querySelector('.js-bulk-panel');
    const master = scope.querySelector('.js-bulk-master');
    const selectAll = scope.querySelector('.js-check-all');

    scope.querySelectorAll('.js-bulk-row').forEach(row => {
      const checkbox = row.querySelector('.js-bulk-check');
      row.classList.toggle('is-selected', Boolean(checkbox?.checked));
    });

    scope.classList.toggle('has-bulk-selection', selectedCount > 0);
    if (panel) panel.classList.toggle('d-none', selectedCount === 0);
    scope.querySelectorAll('.js-bulk-count').forEach(node => { node.textContent = String(selectedCount); });
    scope.querySelectorAll('.js-bulk-label').forEach(node => { node.textContent = label; });
    scope.querySelectorAll('.js-bulk-submit').forEach(button => {
      button.disabled = selectedCount === 0;
      if (button.dataset.confirm) {
        button.dataset.confirmResolved = normalizeConfirmText(button.dataset.confirm)
          .replaceAll('{count}', String(selectedCount))
          .replaceAll('{label}', label);
      }
    });
    syncBulkExportForm(scope);
    syncBulkPersistedInputs(scope);
    scope.querySelectorAll('.js-glass-bulk-action').forEach(button => {
      button.classList.toggle('d-none', selectedCount === 0);
    });

    if (master) {
      master.checked = checks.length > 0 && visibleSelectedCount === checks.length;
      master.indeterminate = visibleSelectedCount > 0 && visibleSelectedCount < checks.length;
    }
    if (selectAll) {
      selectAll.textContent = checks.length > 0 && visibleSelectedCount === checks.length ? 'Снять выбор' : 'Выбрать все';
    }
  };


  document.querySelectorAll('.js-excel-options-toggle').forEach(button => {
    button.addEventListener('click', () => {
      const target = document.querySelector(button.dataset.target || '');
      if (!target) return;
      target.classList.toggle('d-none');
      const isOpen = !target.classList.contains('d-none');
      button.classList.toggle('is-active', isOpen);
      button.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      if (isOpen) {
        target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    });
  });

  const initBulkSelectableScope = (scope) => {
    if (!(scope instanceof HTMLElement)) return;
    const checks = Array.from(scope.querySelectorAll('.js-bulk-check'));
    const storedSelection = readBulkSelection(scope);
    if (bulkStorageKey(scope)) {
      scope.__bulkSelectedIds = storedSelection ?? new Set(checks.filter(check => check.checked).map(check => String(check.value || '')).filter(Boolean));
      if (storedSelection !== null) {
        checks.forEach(check => {
          check.checked = storedSelection.has(String(check.value));
        });
      }
      if (scope.dataset.selectionStorage === 'local' && storedSelection && storedSelection.size > 0) {
        const panel = scope.querySelector('[data-excel-options-panel]');
        const toggle = document.querySelector(`.js-excel-options-toggle[data-target="#${panel?.id}"]`);
        panel?.classList.remove('d-none');
        toggle?.classList.add('is-active');
        toggle?.setAttribute('aria-expanded', 'true');
      }
      syncBulkExportForm(scope);
      syncBulkPersistedInputs(scope);
    }
    const setAll = (checked) => {
      Array.from(scope.querySelectorAll('.js-bulk-check')).filter(isBulkCheckAvailable).forEach(check => {
        check.checked = checked;
        if (scope.__bulkSelectedIds instanceof Set) {
          const taskId = String(check.value || '');
          if (taskId) {
            if (checked) scope.__bulkSelectedIds.add(taskId);
            else scope.__bulkSelectedIds.delete(taskId);
          }
        }
        check.dispatchEvent(new Event('change', { bubbles: true }));
      });
      writeBulkSelection(scope);
      syncBulkScope(scope);
    };

    const master = scope.querySelector('.js-bulk-master');
    if (master && master.dataset.bulkBound !== '1') {
      master.addEventListener('change', event => {
        setAll(event.currentTarget.checked);
      });
      master.dataset.bulkBound = '1';
    }

    scope.querySelectorAll('.js-bulk-clear').forEach(button => {
      if (button.dataset.bulkBound === '1') return;
      button.addEventListener('click', () => {
        if (scope.__bulkSelectedIds instanceof Set) {
          scope.__bulkSelectedIds.clear();
          Array.from(scope.querySelectorAll('.js-bulk-check')).forEach(check => { check.checked = false; });
          writeBulkSelection(scope);
          syncBulkScope(scope);
          return;
        }
        setAll(false);
      });
      button.dataset.bulkBound = '1';
    });

    checks.forEach(check => {
      if (check.dataset.bulkBound === '1') return;
      check.addEventListener('click', event => event.stopPropagation());
      check.addEventListener('change', () => {
        if (scope.__bulkSelectedIds instanceof Set) {
          const taskId = String(check.value || '');
          if (taskId) {
            if (check.checked) scope.__bulkSelectedIds.add(taskId);
            else scope.__bulkSelectedIds.delete(taskId);
            writeBulkSelection(scope);
          }
        }
        syncBulkScope(scope);
      });
      check.dataset.bulkBound = '1';
    });

    scope.querySelectorAll('.js-bulk-row').forEach(row => {
      if (row.dataset.bulkBound === '1') return;
      let openTimer = null;
      row.addEventListener('click', event => {
        if (event.target.closest('a, button, input, textarea, select, label, [role="button"]')) return;
        if (scope.dataset.bulkRowClick === 'open') {
          const hasActiveSelection = Array.from(scope.querySelectorAll('.js-bulk-check')).some(check => check.checked && !check.disabled);
          if (hasActiveSelection) {
            const checkbox = row.querySelector('.js-bulk-check');
            if (!checkbox || checkbox.disabled) return;
            checkbox.checked = !checkbox.checked;
            checkbox.dispatchEvent(new Event('change', { bubbles: true }));
            return;
          }
          const href = row.dataset.href;
          if (href) {
            window.clearTimeout(openTimer);
            openTimer = window.setTimeout(() => {
              clearAllBulkSelectionStorage();
              window.location.href = href;
            }, 220);
          }
          return;
        }
        const checkbox = row.querySelector('.js-bulk-check');
        if (!checkbox || checkbox.disabled) return;
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
      });
      row.addEventListener('dblclick', event => {
        if (!scope.dataset.bulkRowDblclick) return;
        if (event.target.closest('a, button, input, textarea, select, label, [role="button"]')) return;
        event.preventDefault();
        window.clearTimeout(openTimer);
        if (scope.dataset.bulkRowDblclick === 'select') {
          const checkbox = row.querySelector('.js-bulk-check');
          if (!checkbox || checkbox.disabled) return;
          checkbox.checked = !checkbox.checked;
          checkbox.dispatchEvent(new Event('change', { bubbles: true }));
          return;
        }
        if (scope.dataset.bulkRowDblclick === 'delete') {
          row.querySelector('.js-row-delete-action')?.click();
        }
      });
      row.dataset.bulkBound = '1';
    });

    syncBulkScope(scope);
  };

  document.querySelectorAll('.js-bulk-selectable').forEach(initBulkSelectableScope);
  document.addEventListener('crm:ajax-pagination-updated', event => {
    (event.detail?.content || document).querySelectorAll?.('.js-bulk-selectable').forEach(initBulkSelectableScope);
  });

  document.querySelectorAll('.js-remark-export-scope').forEach(scope => {
    const premiseStorageKey = scope.dataset.premiseStorageKey || (scope.dataset.selectionKey ? `crm-premise-visibility:${scope.dataset.selectionKey}` : '');
    const premiseStorage = scope.dataset.selectionStorage === 'local' ? window.localStorage : window.sessionStorage;
    const exportFormSelector = scope.dataset.exportForm || '';
    const exportForm = exportFormSelector ? document.querySelector(exportFormSelector) : null;
    const premiseInputs = Array.from(scope.querySelectorAll('.js-premise-visibility'));
    const readPremiseSelection = () => {
      if (!premiseStorageKey) return null;
      try {
        const raw = premiseStorage.getItem(premiseStorageKey);
        if (raw === null) return null;
        const values = JSON.parse(raw || '[]');
        return Array.isArray(values) ? new Set(values.map(String)) : null;
      } catch (error) {
        return null;
      }
    };
    const writePremiseSelection = (values) => {
      if (!premiseStorageKey) return;
      try {
        premiseStorage.setItem(premiseStorageKey, JSON.stringify(Array.from(values)));
      } catch (error) {}
    };
    const syncPremiseExportForm = (visiblePremises) => {
      if (!exportForm) return;
      exportForm.querySelectorAll('input[name="premise_ids"]').forEach(input => input.remove());
      Array.from(visiblePremises).forEach(premiseId => {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'premise_ids';
        input.value = premiseId;
        exportForm.appendChild(input);
      });
    };
    const updatePremiseOnlyActions = (visiblePremises) => {
      if (scope.dataset.premiseOnlySelection !== '1') return;
      const exportButtons = scope.querySelectorAll('.js-contractor-export-submit');
      exportButtons.forEach(button => {
        button.disabled = visiblePremises.size === 0;
      });
    };
    const syncPremiseCount = (visiblePremises) => {
      const count = visiblePremises.size;
      if (!scope.querySelector('.js-premise-selection-count')) {
        const host = scope.querySelector('.assignment-section-title > div');
        if (host) {
          const note = document.createElement('small');
          note.className = 'remarks-selection-count js-premise-selection-count';
          host.appendChild(note);
        }
      }
      scope.querySelectorAll('.js-premise-selection-count').forEach(node => {
        node.textContent = `(Выбрано ${count})`;
      });
    };
    const applyStoredPremiseVisibilityToRows = (visiblePremises) => {
      scope.querySelectorAll('.js-bulk-row[data-apartment-id]').forEach(row => {
        const apartmentId = String(row.dataset.apartmentId || '');
        row.hidden = visiblePremises !== null && apartmentId ? !visiblePremises.has(apartmentId) : false;
      });
      const master = scope.querySelector('.js-bulk-master');
      if (master) {
        const visibleChecks = Array.from(scope.querySelectorAll('.js-bulk-row:not([hidden]) .js-bulk-check')).filter(check => !check.disabled);
        master.disabled = visibleChecks.length === 0;
      }
    };
    if (!premiseInputs.length) {
      const storedPremises = readPremiseSelection();
      syncPremiseExportForm(storedPremises || new Set());
      updatePremiseOnlyActions(storedPremises || new Set());
      syncPremiseCount(storedPremises || new Set());
      applyStoredPremiseVisibilityToRows(storedPremises);
      window.addEventListener('pageshow', () => {
        const refreshedPremises = readPremiseSelection();
        syncPremiseExportForm(refreshedPremises || new Set());
        updatePremiseOnlyActions(refreshedPremises || new Set());
        syncPremiseCount(refreshedPremises || new Set());
        applyStoredPremiseVisibilityToRows(refreshedPremises);
        syncBulkScope(scope);
      });
      syncBulkScope(scope);
      return;
    }
    const storedPremises = readPremiseSelection();
    if (storedPremises && premiseInputs.length) {
      premiseInputs.forEach(input => {
        input.checked = storedPremises.has(String(input.value));
      });
    }
    scope.querySelectorAll('.js-contractor-export-submit').forEach(button => {
      button.classList.add('d-none');
    });
    const syncPremiseVisibility = () => {
      const visiblePremises = new Set(
        Array.from(scope.querySelectorAll('.js-premise-visibility:checked')).map(input => String(input.value))
      );
      writePremiseSelection(visiblePremises);
      syncPremiseExportForm(visiblePremises);
      updatePremiseOnlyActions(visiblePremises);
      syncPremiseCount(visiblePremises);
      scope.querySelectorAll('.js-bulk-row[data-apartment-id]').forEach(row => {
        const apartmentId = String(row.dataset.apartmentId || '');
        const visible = !apartmentId || visiblePremises.has(apartmentId);
        row.hidden = !visible;
        if (!visible) {
          const checkbox = row.querySelector('.js-bulk-check');
          if (checkbox && checkbox.checked) {
            checkbox.checked = false;
            checkbox.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
      });
      const visibleChecks = Array.from(scope.querySelectorAll('.js-bulk-row:not([hidden]) .js-bulk-check')).filter(check => !check.disabled);
      const master = scope.querySelector('.js-bulk-master');
      if (master) master.disabled = visibleChecks.length === 0;
      syncBulkScope(scope);
    };
    scope.querySelectorAll('.js-contractor-premise-reset').forEach(button => {
      button.addEventListener('click', () => {
        premiseInputs.forEach(input => {
          input.checked = true;
        });
        syncPremiseVisibility();
      });
    });
    scope.querySelectorAll('.js-premise-visibility').forEach(input => {
      input.addEventListener('change', syncPremiseVisibility);
    });
    window.addEventListener('pageshow', () => {
      const refreshedPremises = readPremiseSelection();
      if (refreshedPremises && premiseInputs.length) {
        premiseInputs.forEach(input => {
          input.checked = refreshedPremises.has(String(input.value));
        });
      }
      syncPremiseVisibility();
    });
    syncPremiseVisibility();
  });

  const escapeAssignmentHtml = value => String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

  const assignmentTaskLabel = (value) => {
    const count = Math.abs(Number.parseInt(value || 0, 10));
    const mod10 = count % 10;
    const mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return `${value} задача`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${value} задачи`;
    return `${value} задач`;
  };

  const syncIssuedFilterBadge = (selector, total) => {
    if (!Number.isFinite(Number(total))) return;
    const link = document.querySelector(selector);
    if (!link) return;
    let badge = link.querySelector(':scope > span');
    if (Number(total) > 0) {
      if (!badge) {
        badge = document.createElement('span');
        link.appendChild(badge);
      }
      badge.textContent = String(total);
    } else {
      badge?.remove();
    }
  };

  const ensureIssuedEmptyState = () => {
    const layout = document.querySelector('.assignment-issued-layout');
    if (!layout || layout.querySelector('.assignment-issued-row, .assignment-issued-empty')) return;
    const overdue = layout.classList.contains('assignment-overdue-layout');
    const empty = document.createElement('div');
    empty.className = `card content-card assignment-issued-empty${overdue ? ' assignment-overdue-empty' : ''}`;
    empty.innerHTML = `
      <div class="card-body text-center text-muted py-5">
        <i class="bi ${overdue ? 'bi-check2-circle' : 'bi-inbox'}"></i>
        <div>${overdue ? 'Просроченных невыполненных задач нет.' : 'Выданных задач за выбранный день пока нет.'}</div>
      </div>`;
    layout.replaceChildren(empty);
  };

  const refreshIssuedCountsAfterRemoval = (row, payload = {}) => {
    const card = row.closest('.assignment-issued-card');
    const dayGroup = row.closest('.assignment-overdue-day-group');
    row.remove();
    if (card) {
      const rowsLeft = card.querySelectorAll('.assignment-issued-row').length;
      const count = card.querySelector('.assignment-issued-count');
      if (count) count.textContent = assignmentTaskLabel(rowsLeft);
      if (!rowsLeft) card.remove();
    }
    if (dayGroup) {
      const dayRowsLeft = dayGroup.querySelectorAll('.assignment-issued-row').length;
      const dayCount = dayGroup.querySelector('.assignment-overdue-day-head strong');
      if (dayCount) dayCount.textContent = assignmentTaskLabel(dayRowsLeft);
      if (!dayRowsLeft) dayGroup.remove();
    }
    syncIssuedFilterBadge('.assignment-filter-pill[href*="issued_day=overdue"]', payload.overdue_total);
    syncIssuedFilterBadge('.assignment-subtab[href*="view=issued"]', payload.issued_total);
    ensureIssuedEmptyState();
  };

  const isOverdueIssuedView = () => Boolean(document.querySelector('.assignment-overdue-layout'));

  const assignmentOverdueDaysText = (isoDate) => {
    if (!isoDate) return '';
    const parts = String(isoDate).split('-').map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return '';
    const target = new Date(parts[0], parts[1] - 1, parts[2]);
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const diff = Math.floor((todayStart - target) / 86400000);
    return diff > 0 ? `просрочено ${diff} дн.` : '';
  };

  const renderIssuedDateCell = (dateCell, payload) => {
    if (!dateCell) return;
    const label = payload?.planned_date || '—';
    const overdueText = payload?.is_overdue ? assignmentOverdueDaysText(payload.planned_date_iso) : '';
    dateCell.innerHTML = `<span>${escapeAssignmentHtml(label)}</span>${overdueText ? `<small class="assignment-overdue-days">${escapeAssignmentHtml(overdueText)}</small>` : ''}`;
  };

  const nativeSubmitAssignmentAction = (form, submitter) => {
    if (!form) return;
    if (submitter?.name) {
      let hidden = Array.from(form.querySelectorAll('input.js-native-submit-value[type="hidden"]')).find(input => input.name === submitter.name);
      if (!hidden) {
        hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = submitter.name;
        hidden.className = 'js-native-submit-value';
        form.appendChild(hidden);
      }
      hidden.value = submitter.value || '';
    }
    form.dataset.assignmentNativeSubmit = '1';
    form.submit();
  };

  const fetchAssignmentAction = async (form, body) => {
    if (!form || !form.action || !window.fetch) {
      const error = new Error('Native submit required');
      error.name = 'AbortError';
      throw error;
    }
    const response = await fetch(form.action, {
      method: 'POST',
      body,
      credentials: 'same-origin',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json',
      },
    });
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      const error = new Error('Native submit required');
      error.name = 'AbortError';
      throw error;
    }
    const data = await response.json();
    if (!response.ok || data.ok === false) {
      throw new Error(data.message || 'Не удалось сохранить изменения');
    }
    return data;
  };

  const submitIssuedAssignmentAction = async (form, submitter) => {
    if (!form || !submitter || !submitter.name) return false;
    if (submitter.dataset.pending === '1') return false;

    const confirmMessage = submitter.dataset.assignmentConfirm;
    if (confirmMessage) {
      const confirmed = await window.crmShowConfirm({
        title: submitter.dataset.assignmentConfirmTitle || 'Подтвердите действие',
        message: confirmMessage,
        okText: submitter.dataset.assignmentConfirmOk || 'Подтвердить',
        danger: true,
      });
      if (!confirmed) return false;
    }

    const body = new FormData(form);
    if (submitter.name && submitter.value) {
      body.set(submitter.name, submitter.value);
    }

    submitter.dataset.pending = '1';
    submitter.disabled = true;
    try {
      const data = await fetchAssignmentAction(form, body);
      const row = form.closest('.assignment-issued-row');
      if (row) {
        if (submitter.name === 'toggle_employee_status_task_id') {
          const statusButton = form.querySelector('.assignment-status-toggle');
          if (statusButton) {
            statusButton.textContent = data.status_label || statusButton.textContent;
            statusButton.className = `badge assignment-status-toggle bg-${data.status_class || 'secondary'}`;
          }
          row.classList.toggle('done-task', Boolean(data.is_done));
        } else if (submitter.name === 'update_date_task_id') {
          renderIssuedDateCell(row.querySelector('.assignment-issued-date-cell'), data);
        }
      }
      showCrmNotice(data.message || 'Изменения сохранены', 'success');
      return true;
    } catch (error) {
      if (error.name === 'AbortError') {
        nativeSubmitAssignmentAction(form, submitter);
        return false;
      }
      showCrmNotice(error.message || 'Не удалось сохранить изменения', 'danger');
      return false;
    } finally {
      submitter.disabled = false;
      delete submitter.dataset.pending;
    }
  };

  const assignmentForm = document.querySelector('.assignment-shell');
  if (assignmentForm) {
    assignmentForm.addEventListener('submit', event => {
      if (event.currentTarget.dataset.assignmentNativeSubmit === '1') return;
      const submitter = event.submitter;
      const form = event.currentTarget;

      if (submitter?.name === 'action' && submitter.value === 'bulk_assign') {
        const selected = Array.from(form.querySelectorAll('.js-bulk-check:checked:not(:disabled)'));
        const responsibleSelect = form.querySelector('select[name="responsible_id"]');
        if (form.dataset.bulkAssignPending === '1') {
          event.preventDefault();
          showCrmNotice('Задачи уже отправляются. Подождите несколько секунд.', 'info');
          return;
        }
        if (!selected.length) {
          event.preventDefault();
          showCrmNotice('Выберите хотя бы одну задачу', 'warning');
          return;
        }
        if (!responsibleSelect?.value) {
          event.preventDefault();
          const responsibleShell = responsibleSelect?.closest('.js-developer-custom-select');
          responsibleSelect?.classList.add('is-invalid');
          responsibleShell?.classList.add('is-invalid');
          responsibleShell?.querySelector('.developer-select-button')?.focus();
          if (!responsibleShell) responsibleSelect?.focus();
          showCrmNotice('Выберите исполнителя. Отмеченные задачи останутся выбранными.', 'warning');
          return;
        }
        form.dataset.bulkAssignPending = '1';
        submitter.disabled = true;
        submitter.classList.add('disabled');
        const textNode = submitter.querySelector('span');
        if (textNode) textNode.textContent = 'Выдаём...';
      }
    });

    assignmentForm.querySelector('select[name="responsible_id"]')?.addEventListener('change', event => {
      event.currentTarget.classList.remove('is-invalid');
      event.currentTarget.closest('.js-developer-custom-select')?.classList.remove('is-invalid');
    });
  }

  const refreshIssuedGroupState = (row) => {
    const card = row.closest('.assignment-issued-card');
    if (!card) return;
    const rowsLeft = card.querySelectorAll('.assignment-issued-row').length;
    const count = card.querySelector('.assignment-issued-count');
    if (count) count.textContent = assignmentTaskLabel(rowsLeft);
    if (!rowsLeft) card.remove();
  };

  const isDesktopAssignmentAction = () => {
    if (document.documentElement.classList.contains('mobile-viewport')
      || document.documentElement.classList.contains('adaptive-mobile-viewport')
      || document.documentElement.classList.contains('touch-app-device')) {
      return false;
    }
    return document.documentElement.classList.contains('desktop-like-pointer')
      || window.matchMedia?.('(min-width: 768px) and (hover: hover) and (pointer: fine)').matches;
  };

  const submitChangeAssigneeForm = async (changeAssigneeForm, submitter = null) => {
    if (!changeAssigneeForm || changeAssigneeForm.dataset.pending === '1') return;

    const changeAssigneeModal = changeAssigneeForm.closest('#assignmentChangeAssigneeModal');
    const selected = changeAssigneeForm.querySelector('input[name="new_responsible_id"]:checked:not(:disabled)');
    if (!selected) {
      showCrmNotice('Выберите нового исполнителя', 'warning');
      return;
    }

    const saveButton = submitter || changeAssigneeForm.querySelector('button[type="submit"]');
    const previousHtml = saveButton?.innerHTML || '';
    changeAssigneeForm.dataset.pending = '1';
    if (saveButton) {
      saveButton.disabled = true;
      saveButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Сохраняем';
    }

    try {
      const data = await fetchAssignmentAction(changeAssigneeForm, new FormData(changeAssigneeForm));
      window.bootstrap?.Modal?.getOrCreateInstance(changeAssigneeModal)?.hide();
      if (window.crmRefreshIssuedAssignments) {
        await window.crmRefreshIssuedAssignments();
      }
      showCrmNotice(data.message || 'Исполнитель изменён', 'success');
    } catch (error) {
      showCrmNotice(error.message || 'Не удалось изменить исполнителя', 'danger');
    } finally {
      delete changeAssigneeForm.dataset.pending;
      if (saveButton) {
        saveButton.disabled = false;
        saveButton.innerHTML = previousHtml;
      }
    }
  };

  const initAssignmentChangeAssigneeModal = () => {
    const changeAssigneeModal = document.getElementById('assignmentChangeAssigneeModal');
    if (!changeAssigneeModal) return null;

    // Bootstrap appends its backdrop directly to <body>. Keep the modal there
    // as well so page-entry stacking contexts cannot place the backdrop above
    // the dialog and intercept every click.
    if (changeAssigneeModal.parentElement !== document.body) {
      document.body.append(changeAssigneeModal);
    }

    if (changeAssigneeModal.dataset.assignmentChangeAssigneeReady === '1') {
      return changeAssigneeModal;
    }
    changeAssigneeModal.dataset.assignmentChangeAssigneeReady = '1';

    changeAssigneeModal.addEventListener('show.bs.modal', event => {
      const button = event.relatedTarget?.closest?.('.js-assignment-change-assignee-open') || event.relatedTarget;
      const taskId = button?.dataset?.taskId || '';
      const room = button?.dataset?.room || '—';
      const taskText = button?.dataset?.taskText || '—';
      const currentId = button?.dataset?.currentResponsibleId || '';
      const currentName = button?.dataset?.currentResponsibleName || '—';

      const taskIdInput = changeAssigneeModal.querySelector('.js-change-assignee-task-id');
      if (taskIdInput) taskIdInput.value = taskId;
      const roomEl = changeAssigneeModal.querySelector('.js-change-assignee-room');
      const currentEl = changeAssigneeModal.querySelector('.js-change-assignee-current');
      const taskTextEl = changeAssigneeModal.querySelector('.js-change-assignee-task-text');
      if (roomEl) roomEl.textContent = room;
      if (currentEl) currentEl.textContent = currentName;
      if (taskTextEl) taskTextEl.textContent = taskText;

      changeAssigneeModal.querySelectorAll('input[name="new_responsible_id"]').forEach(input => {
        const isCurrent = Boolean(currentId) && input.value === currentId;
        input.checked = false;
        input.disabled = isCurrent;
        const option = input.closest('.assignment-change-assignee-option');
        option?.classList.toggle('is-current', isCurrent);
      });
      window.setTimeout(() => {
        const first = changeAssigneeModal.querySelector('input[name="new_responsible_id"]:not(:disabled)');
        first?.focus();
      }, 120);
    });

    changeAssigneeModal.addEventListener('change', event => {
      const input = event.target.closest?.('input[name="new_responsible_id"]');
      if (!input || !changeAssigneeModal.contains(input)) return;
      const list = input.closest('.assignment-change-assignee-list');
      list?.querySelectorAll('.assignment-change-assignee-option').forEach(option => {
        const optionInput = option.querySelector('input[name="new_responsible_id"]');
        option.classList.toggle('is-picked', Boolean(optionInput?.checked));
      });
    });

    return changeAssigneeModal;
  };

  // The issued tab is injected without a page reload. Capture these two
  // actions at document level so newly injected modal forms cannot fall back
  // to a native navigation before their local initializer runs.
  document.addEventListener('submit', event => {
    const changeAssigneeForm = event.target.closest?.('.assignment-change-assignee-card');
    if (!changeAssigneeForm || !isDesktopAssignmentAction()) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    void submitChangeAssigneeForm(changeAssigneeForm, event.submitter);
  }, true);

  window.crmInitAssignmentChangeAssigneeModal = initAssignmentChangeAssigneeModal;
  initAssignmentChangeAssigneeModal();

  const pad2 = value => String(value).padStart(2, '0');
  const toIsoDate = date => `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
  const parseIsoDate = value => {
    const parts = String(value || '').split('-').map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return new Date();
    return new Date(parts[0], parts[1] - 1, parts[2]);
  };
  const prettyDate = value => {
    try {
      return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).format(parseIsoDate(value));
    } catch (error) {
      return value || '';
    }
  };

  const ensureAssignmentDateModal = () => {
    let modal = document.querySelector('.js-assignment-date-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'assignment-date-modal-overlay js-assignment-date-modal d-none';
    modal.innerHTML = `
      <div class="assignment-date-modal" role="dialog" aria-modal="true" aria-labelledby="assignment-date-modal-title">
        <div class="assignment-date-modal-head">
          <div>
            <div class="assignment-date-modal-kicker">Дата выполнения</div>
            <h2 id="assignment-date-modal-title">Изменить дату задачи</h2>
          </div>
          <button class="assignment-date-modal-close js-assignment-date-cancel" type="button" aria-label="Закрыть"><i class="bi bi-x-lg"></i></button>
        </div>
        <div class="assignment-date-quick-row">
          <button type="button" class="js-assignment-date-quick" data-offset="0">Сегодня</button>
          <button type="button" class="js-assignment-date-quick" data-offset="1">Завтра</button>
          <button type="button" class="js-assignment-date-quick" data-offset="3">+3 дня</button>
        </div>
        <div class="assignment-date-calendar">
          <div class="assignment-date-calendar-head">
            <button type="button" class="assignment-date-nav js-assignment-date-prev" aria-label="Предыдущий месяц"><i class="bi bi-chevron-left"></i></button>
            <div class="assignment-date-month js-assignment-date-month"></div>
            <button type="button" class="assignment-date-nav js-assignment-date-next" aria-label="Следующий месяц"><i class="bi bi-chevron-right"></i></button>
          </div>
          <div class="assignment-date-weekdays"><span>Пн</span><span>Вт</span><span>Ср</span><span>Чт</span><span>Пт</span><span>Сб</span><span>Вс</span></div>
          <div class="assignment-date-grid js-assignment-date-grid"></div>
        </div>
        <div class="assignment-date-selected">
          <span>Выбрано</span>
          <b class="js-assignment-date-selected-text"></b>
        </div>
        <div class="assignment-date-modal-actions">
          <button class="btn btn-outline-secondary js-assignment-date-cancel" type="button">Отмена</button>
          <button class="btn btn-primary js-assignment-date-save" type="button"><i class="bi bi-check2"></i><span>Сохранить дату</span></button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    return modal;
  };

  const openAssignmentDateModal = (button) => {
    const form = button.closest('form');
    const row = button.closest('.assignment-issued-row');
    const taskId = button.dataset.taskId;
    if (!form || !row || !taskId) return;

    const modal = ensureAssignmentDateModal();
    let selectedIso = button.dataset.currentDate || toIsoDate(new Date());
    let viewDate = parseIsoDate(selectedIso);
    viewDate.setDate(1);

    const monthEl = modal.querySelector('.js-assignment-date-month');
    const gridEl = modal.querySelector('.js-assignment-date-grid');
    const selectedText = modal.querySelector('.js-assignment-date-selected-text');
    const saveBtn = modal.querySelector('.js-assignment-date-save');

    const render = () => {
      const monthLabel = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(viewDate);
      monthEl.textContent = monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1);
      selectedText.textContent = prettyDate(selectedIso);
      gridEl.innerHTML = '';

      const year = viewDate.getFullYear();
      const month = viewDate.getMonth();
      const first = new Date(year, month, 1);
      const firstWeekDay = (first.getDay() + 6) % 7;
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const todayIso = toIsoDate(new Date());

      for (let i = 0; i < firstWeekDay; i += 1) {
        const spacer = document.createElement('span');
        spacer.className = 'assignment-date-day-spacer';
        gridEl.appendChild(spacer);
      }
      for (let day = 1; day <= daysInMonth; day += 1) {
        const date = new Date(year, month, day);
        const iso = toIsoDate(date);
        const dayButton = document.createElement('button');
        dayButton.type = 'button';
        dayButton.className = 'assignment-date-day';
        dayButton.textContent = String(day);
        dayButton.classList.toggle('is-selected', iso === selectedIso);
        dayButton.classList.toggle('is-today', iso === todayIso);
        dayButton.addEventListener('click', () => {
          selectedIso = iso;
          render();
        });
        gridEl.appendChild(dayButton);
      }
    };

    const close = () => {
      modal.classList.add('d-none');
      document.removeEventListener('keydown', onKeydown);
    };
    const onKeydown = event => {
      if (event.key === 'Escape') close();
    };

    modal.querySelectorAll('.js-assignment-date-cancel').forEach(cancel => {
      cancel.onclick = close;
    });
    modal.querySelector('.js-assignment-date-prev').onclick = () => {
      viewDate.setMonth(viewDate.getMonth() - 1);
      render();
    };
    modal.querySelector('.js-assignment-date-next').onclick = () => {
      viewDate.setMonth(viewDate.getMonth() + 1);
      render();
    };
    modal.querySelectorAll('.js-assignment-date-quick').forEach(quick => {
      quick.onclick = () => {
        const next = new Date();
        next.setDate(next.getDate() + Number(quick.dataset.offset || 0));
        selectedIso = toIsoDate(next);
        viewDate = parseIsoDate(selectedIso);
        viewDate.setDate(1);
        render();
      };
    });
    modal.onclick = event => {
      if (event.target === modal) close();
    };
    saveBtn.onclick = async () => {
      const body = new FormData();
      const csrf = form.querySelector('input[name="csrf_token"]')?.value || getCsrfToken();
      if (csrf) body.append('csrf_token', csrf);
      body.append(`planned_date_${taskId}`, selectedIso);
      body.append('update_date_task_id', taskId);

      saveBtn.disabled = true;
      try {
        const resp = await fetch(form.action || window.location.href, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
          credentials: 'same-origin',
          body,
        });
        const isJson = (resp.headers.get('content-type') || '').includes('application/json');
        const data = isJson ? await resp.json().catch(() => ({})) : { ok: false, message: 'Сервер вернул не JSON-ответ. Обновите страницу и попробуйте ещё раз.' };
        if (!resp.ok || !data.ok) {
          showCrmNotice(data.message || 'Не удалось изменить дату', 'danger');
          return;
        }
        renderIssuedDateCell(row.querySelector('.assignment-issued-date-cell'), data);
        button.dataset.currentDate = data.planned_date_iso || selectedIso;
        close();
        showCrmNotice(data.message || 'Дата выполнения изменена', 'success');
      } catch (error) {
        showCrmNotice(error?.message || 'Не удалось изменить дату. Проверьте соединение и попробуйте ещё раз.', 'danger');
      } finally {
        saveBtn.disabled = false;
      }
    };

    render();
    document.addEventListener('keydown', onKeydown);
    modal.classList.remove('d-none');
  };

  // The issued-day tabs replace their cards without reloading the page. Keep
  // this handler delegated so newly inserted "Date" buttons work as well.
  document.addEventListener('click', event => {
    const button = event.target.closest?.('.js-assignment-date-open');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    openAssignmentDateModal(button);
  }, true);

  const removeIssuedAssignment = async (form, button) => {
    if (!form || button?.dataset.pending === '1') return;

    const confirmed = await window.crmShowConfirm({
      title: 'Удалить задачу у сотрудника',
      message: 'Задача будет снята с пользователя и снова станет доступна без исполнителя и даты выполнения.',
      okText: 'Удалить',
      danger: true,
    });
    if (!confirmed) return;

    if (!window.fetch) {
      form.dataset.assignmentNativeSubmit = '1';
      form.submit();
      return;
    }

    const previousDisabled = Boolean(button?.disabled);
    if (button) {
      button.dataset.pending = '1';
      button.disabled = true;
    }
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        credentials: 'same-origin',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'application/json',
        },
      });
      const isJson = (response.headers.get('content-type') || '').includes('application/json');
      if (!isJson) {
        if (!response.ok) {
          throw new Error(response.status === 403
            ? 'Нет доступа к удалению задачи. Обновите страницу и войдите снова.'
            : 'Сервер не смог удалить задачу. Попробуйте ещё раз.');
        }
        form.dataset.assignmentNativeSubmit = '1';
        form.submit();
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) {
        throw new Error(data.message || 'Не удалось удалить задачу у сотрудника');
      }
      const row = form.closest('.assignment-issued-row');
      if (row) refreshIssuedCountsAfterRemoval(row, data);
      showCrmNotice(data.message || 'Задача удалена у сотрудника', 'success');
    } catch (error) {
      showCrmNotice(error.message || 'Не удалось удалить задачу у сотрудника', 'danger');
      if (button) button.disabled = previousDisabled;
    } finally {
      if (button) delete button.dataset.pending;
    }
  };

  // Capture the deliberate tap before legacy submit/confirmation handlers.
  // A submit fallback remains for keyboard and assistive-technology users.
  document.addEventListener('click', event => {
    const button = event.target.closest?.('.assignment-remove-user-btn');
    const form = button?.closest?.('.assignment-remove-user-form');
    if (!button || !form) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    void removeIssuedAssignment(form, button);
  }, true);

  document.addEventListener('submit', event => {
    const form = event.target.closest?.('.assignment-remove-user-form');
    if (!form || event.target !== form || form.dataset.assignmentNativeSubmit === '1') return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const button = event.submitter || form.querySelector('.assignment-remove-user-btn');
    void removeIssuedAssignment(form, button);
  });

  document.addEventListener('click', event => {
    const submitter = event.target.closest('button[name="toggle_employee_status_task_id"]');
    if (!submitter) return;
    const form = submitter.closest('form');
    if (!form) return;
    if (form.classList.contains('assignment-issued-actions') || form.classList.contains('assignment-status-toggle-form')) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation?.();
      void submitIssuedAssignmentAction(form, submitter);
      return;
    }
  }, true);

  document.querySelectorAll('.assignment-status-toggle-form, .assignment-issued-actions').forEach(form => {
    form.addEventListener('submit', async event => {
      if (event.currentTarget.dataset.assignmentNativeSubmit === '1') return;
      const submitter = event.submitter;
      if (!submitter || !submitter.name) return;
      event.preventDefault();
      await submitIssuedAssignmentAction(form, submitter);
    });
  });
});

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.crm-toast').forEach(toast => {
    window.clearTimeout(toast._flashTimer);
    toast._flashTimer = window.setTimeout(() => {
      const close = toast.querySelector('[data-bs-dismiss="alert"]');
      if (close) {
        close.click();
      } else {
        toast.remove();
      }
    }, 5000);
  });

  const syncWriteoffQuantityForLine = line => {
    if (!line) return;
    const select = line.querySelector('.js-writeoff-material-select');
    const block = line.querySelector('.js-writeoff-quantity-block');
    const input = line.querySelector('.js-writeoff-quantity-input');
    const unitBadge = line.querySelector('.js-writeoff-unit-badge');
    const balanceHint = line.querySelector('.js-writeoff-balance-hint');
    const option = select?.selectedOptions && select.selectedOptions[0];
    const unit = option?.dataset?.unit || '';
    const balance = option?.dataset?.balance || '';
    const hasMaterial = Boolean(select?.value);
    block?.classList.toggle('d-none', !hasMaterial);
    if (input) {
      input.disabled = !hasMaterial;
      input.required = hasMaterial;
      input.placeholder = unit ? `Введите количество, ${unit}` : 'Введите количество';
    }
    if (unitBadge) unitBadge.textContent = unit ? `ед. изм: ${unit}` : '';
    if (balanceHint) balanceHint.textContent = hasMaterial && balance ? `Доступно к списанию: ${balance} ${unit}` : '';
    if (!hasMaterial && input) {
      input.value = '';
      input.classList.remove('is-invalid');
    }
  };

  const bindWriteoffLine = line => {
    if (!line || line.dataset.writeoffLineBound === '1') return;
    line.dataset.writeoffLineBound = '1';
    const select = line.querySelector('.js-writeoff-material-select');
    const input = line.querySelector('.js-writeoff-quantity-input');
    const removeBtn = line.querySelector('.js-material-line-remove');
    select?.addEventListener('change', () => syncWriteoffQuantityForLine(line));
    input?.addEventListener('input', () => input.classList.remove('is-invalid'));
    removeBtn?.addEventListener('click', () => {
      const container = line.closest('.js-material-lines');
      if (!container) return;
      const lines = Array.from(container.querySelectorAll('.js-material-line'));
      if (lines.length <= 1) {
        const currentSelect = line.querySelector('.js-writeoff-material-select');
        const currentInput = line.querySelector('.js-writeoff-quantity-input');
        if (currentSelect) currentSelect.value = '';
        if (currentInput) currentInput.value = '';
        syncWriteoffQuantityForLine(line);
        return;
      }
      line.remove();
      const nextLines = Array.from(container.querySelectorAll('.js-material-line'));
      nextLines.forEach((item, index) => {
        item.querySelector('.js-material-line-remove')?.classList.toggle('d-none', nextLines.length <= 1 && index === 0);
      });
    });
    syncWriteoffQuantityForLine(line);
  };

  const initMultiMaterialForms = (scope = document) => {
    const forms = [];
    if (scope.matches?.('.js-multi-material-form')) forms.push(scope);
    scope.querySelectorAll?.('.js-multi-material-form').forEach(form => forms.push(form));
    forms.forEach(form => {
    const originalSelect = form.querySelector('.js-writeoff-material-select');
    let originalBlock = form.querySelector('.js-writeoff-quantity-block');
    const fallbackInput = form.querySelector('.js-writeoff-quantity-input, input[name="quantity"]');
    let fallbackQuantityWrap = null;
    let builtQuantityBlockFromFallback = false;
    if (!originalSelect) return;
    const originalSelectShell = originalSelect.closest('.js-developer-custom-select');
    if (!originalBlock && fallbackInput) {
      const sourceWrap = fallbackInput.parentElement;
      if (sourceWrap) {
        fallbackQuantityWrap = sourceWrap;
        builtQuantityBlockFromFallback = true;
        originalBlock = document.createElement('div');
        originalBlock.className = 'js-writeoff-quantity-block';
        const label = sourceWrap.querySelector('.form-label');
        if (label) {
          originalBlock.append(label.cloneNode(true));
        }
        const unitBadge = document.createElement('span');
        unitBadge.className = 'material-unit-pill js-writeoff-unit-badge';
        originalBlock.append(unitBadge);
        const lineInput = fallbackInput.cloneNode(true);
        lineInput.classList.add('js-writeoff-quantity-input');
        originalBlock.append(lineInput);
        const hint = document.createElement('div');
        hint.className = 'form-text js-writeoff-balance-hint';
        originalBlock.append(hint);
      }
    }
    if (!originalBlock) return;
    const selectWrap = originalSelectShell?.parentElement || originalSelect.parentElement;
    if (!selectWrap || selectWrap.dataset.materialLinesReady === '1') return;

    const createLine = (useExisting = false) => {
      const line = document.createElement('div');
      line.className = 'material-line js-material-line';

      const lineSelectHost = useExisting ? (originalSelectShell || originalSelect) : originalSelect.cloneNode(true);
      if (!useExisting) {
        const lineSelect = lineSelectHost;
        lineSelect.value = '';
        lineSelect.required = true;
        lineSelect.classList.remove('developer-native-select', 'mobile-native-select');
        delete lineSelect.dataset.customSelectReady;
        delete lineSelect.dataset.nativeSelect;
        lineSelect.removeAttribute('aria-hidden');
        lineSelect.removeAttribute('tabindex');
      }

      const lineBlock = useExisting ? originalBlock : originalBlock.cloneNode(true);
      lineBlock.classList.add('material-line-quantity');
      lineBlock.classList.add('material-line-quantity-simple');
      if (!useExisting) {
        lineBlock.classList.add('d-none');
        const lineInput = lineBlock.querySelector('.js-writeoff-quantity-input');
        if (lineInput) {
          lineInput.value = '';
          lineInput.disabled = true;
          lineInput.required = false;
        }
      }

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'btn btn-outline-secondary material-line-remove js-material-line-remove d-none';
      removeBtn.setAttribute('aria-label', 'Удалить строку');
      removeBtn.innerHTML = '<i class="bi bi-x-lg"></i>';

      line.append(lineSelectHost, lineBlock, removeBtn);
      return line;
    };

    const container = document.createElement('div');
    container.className = 'material-lines js-material-lines';
    const firstLine = createLine(true);
    container.append(firstLine);

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'btn btn-outline-primary btn-sm mt-3 js-material-line-add';
    addBtn.innerHTML = '<i class="bi bi-plus-lg me-2"></i>Добавить материал';
    addBtn.addEventListener('click', () => {
      const newLine = createLine();
      container.append(newLine);
      bindWriteoffLine(newLine);
      container.querySelectorAll('.js-material-line-remove').forEach(button => button.classList.remove('d-none'));
    });

    const label = selectWrap.querySelector('.form-label');
    if (label) {
      label.textContent = 'Материалы';
    }

    selectWrap.classList.add('material-lines-field');
    selectWrap.append(container, addBtn);
    if (builtQuantityBlockFromFallback && fallbackQuantityWrap && fallbackQuantityWrap !== selectWrap) {
      fallbackQuantityWrap.remove();
    }
    selectWrap.dataset.materialLinesReady = '1';
    bindWriteoffLine(firstLine);
    form.classList.add('is-material-lines-ready');
    });
  };

  const initMaterialManualForms = (scope = document) => {
    const forms = [];
    if (scope.matches?.('.js-material-manual-form')) forms.push(scope);
    scope.querySelectorAll?.('.js-material-manual-form').forEach(form => forms.push(form));
    forms.forEach(form => {
    if (form.dataset.manualAjaxBound === '1') return;
    form.dataset.manualAjaxBound = '1';
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.submitter || form.querySelector('button[type="submit"]');
      const previousHtml = button?.innerHTML || '';
      if (button) button.disabled = true;
      try {
        const response = await fetch(form.action || window.location.href, {
          method: 'POST',
          body: new FormData(form),
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) throw new Error(data.message || 'Не удалось добавить ручное списание');
        const currentDate = form.querySelector('input[name="writeoff_date"]')?.value || '';
        const taskInput = form.querySelector('textarea[name="task_name"]');
        if (taskInput) taskInput.value = '';
        const premiseInput = form.querySelector('input[name="premise_text"]');
        if (premiseInput) premiseInput.value = '';
        const lines = Array.from(form.querySelectorAll('.js-material-line'));
        lines.slice(1).forEach(line => line.remove());
        const firstLine = form.querySelector('.js-material-line');
        if (firstLine) {
          const select = firstLine.querySelector('.js-writeoff-material-select');
          const quantity = firstLine.querySelector('.js-writeoff-quantity-input');
          if (select) {
            select.value = '';
            select.dispatchEvent(new Event('change', { bubbles: true }));
          }
          if (quantity) {
            quantity.value = '';
            quantity.classList.remove('is-invalid');
          }
          firstLine.querySelector('.js-material-line-remove')?.classList.add('d-none');
        }
        const dateInput = form.querySelector('input[name="writeoff_date"]');
        if (dateInput && currentDate) dateInput.value = currentDate;
        showCrmNotice(data.message || 'Ручное списание добавлено', 'success');
      } catch (error) {
        showCrmNotice(error.message || 'Не удалось добавить ручное списание', 'danger');
      } finally {
        if (button) {
          button.disabled = false;
          button.innerHTML = previousHtml;
        }
      }
    });
    });
  };

  initMultiMaterialForms();
  initMaterialManualForms();
  document.addEventListener('crm:ajax-pagination-updated', event => {
    if (event.detail?.pageKey !== 'materials') return;
    const content = event.detail?.content || document;
    initMultiMaterialForms(content);
    initMaterialManualForms(content);
  });
});

// Быстрая пагинация: сервер по-прежнему формирует обычную HTML-страницу,
// поэтому ссылки работают и без JavaScript. В браузере меняем только список
// и две панели навигации, сохраняя шапку, фильтры и обработчики карточек.
(() => {
  const pageCache = new Map();
  let requestController = null;
  let offlineFallbackNoticeAt = 0;
  const offlineFallbackMessage = window.__CRM_OFFLINE_MESSAGE__ || 'Не удается обновить. Показана сохраненная версия.';
  const showOfflineFallbackNotice = () => {
    const now = Date.now();
    if (now - offlineFallbackNoticeAt < 4000) return;
    offlineFallbackNoticeAt = now;
    if (typeof window.crmShowOfflineFallback === 'function') {
      window.crmShowOfflineFallback();
    }
    if (typeof showCrmNotice === 'function') {
      showCrmNotice(offlineFallbackMessage, 'warning');
    }
  };

  const isCompatibleNode = (currentNode, nextNode) => {
    if (!currentNode || !nextNode || currentNode.nodeType !== nextNode.nodeType) return false;
    if (currentNode.nodeType !== Node.ELEMENT_NODE) return true;
    return currentNode.tagName === nextNode.tagName;
  };

  const syncElementAttributes = (currentElement, nextElement) => {
    Array.from(currentElement.attributes).forEach(attribute => {
      if (!nextElement.hasAttribute(attribute.name)) currentElement.removeAttribute(attribute.name);
    });
    Array.from(nextElement.attributes).forEach(attribute => {
      if (currentElement.getAttribute(attribute.name) !== attribute.value) {
        currentElement.setAttribute(attribute.name, attribute.value);
      }
    });

    if (currentElement instanceof HTMLInputElement && nextElement instanceof HTMLInputElement) {
      currentElement.value = nextElement.value;
      currentElement.checked = nextElement.checked;
      currentElement.disabled = nextElement.disabled;
    } else if (currentElement instanceof HTMLTextAreaElement && nextElement instanceof HTMLTextAreaElement) {
      currentElement.value = nextElement.value;
    }
  };

  const morphPaginationNode = (currentNode, nextNode) => {
    if (!isCompatibleNode(currentNode, nextNode)) {
      currentNode.replaceWith(nextNode.cloneNode(true));
      return;
    }
    if (currentNode.nodeType === Node.TEXT_NODE || currentNode.nodeType === Node.COMMENT_NODE) {
      if (currentNode.nodeValue !== nextNode.nodeValue) currentNode.nodeValue = nextNode.nodeValue;
      return;
    }

    syncElementAttributes(currentNode, nextNode);
    const currentChildren = Array.from(currentNode.childNodes);
    const nextChildren = Array.from(nextNode.childNodes);
    nextChildren.forEach((nextChild, index) => {
      const currentChild = currentChildren[index];
      if (!currentChild) {
        currentNode.appendChild(nextChild.cloneNode(true));
        return;
      }
      morphPaginationNode(currentChild, nextChild);
    });
    currentChildren.slice(nextChildren.length).forEach(extraChild => {
      if (extraChild.nodeType === Node.ELEMENT_NODE) {
        extraChild.hidden = true;
        extraChild.setAttribute('data-ajax-pagination-spare', '1');
      } else {
        extraChild.remove();
      }
    });

    if (currentNode instanceof HTMLSelectElement && nextNode instanceof HTMLSelectElement) {
      currentNode.value = nextNode.value;
    }
  };

  const fetchPageText = async (url, signal, useCache = true) => {
    const cacheKey = url.toString();
    if (useCache && pageCache.has(cacheKey)) return pageCache.get(cacheKey);
    const response = await fetch(cacheKey, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CRM-Partial-Navigation': '1' },
      signal,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (response.headers.get('X-CRM-Offline-Fallback') === '1') {
      showOfflineFallbackNotice();
    } else if (typeof window.crmHideOfflineFallback === 'function' && navigator.onLine) {
      window.crmHideOfflineFallback();
    }
    const text = await response.text();
    if (useCache) pageCache.set(cacheKey, text);
    return text;
  };

  const prefetchPaginationLinks = pageRoot => {
    pageRoot.querySelectorAll('[data-ajax-pagination-nav] a[href]').forEach(link => {
      const href = link.getAttribute('href') || '';
      if (!href || href === '#') return;
      const url = new URL(href, window.location.href);
      if (url.origin !== window.location.origin) return;
      fetchPageText(url).catch(() => {});
    });
  };

  const updatePaginationPage = async (targetUrl, { push = true, scroll = true, useCache = true, root = null } = {}) => {
    const currentRoot = root || document.querySelector('[data-ajax-pagination-page]');
    if (!currentRoot) {
      window.location.assign(targetUrl.toString());
      return;
    }
    const pageKey = currentRoot.dataset.ajaxPaginationPage || '';
    requestController?.abort();
    requestController = new AbortController();
    currentRoot.classList.add('ajax-pagination-loading');
    currentRoot.setAttribute('aria-busy', 'true');

    try {
      const html = await fetchPageText(targetUrl, requestController.signal, useCache);
      const nextDocument = new DOMParser().parseFromString(html, 'text/html');
      const nextRoot = nextDocument.querySelector(`[data-ajax-pagination-page="${CSS.escape(pageKey)}"]`);
      const currentContent = currentRoot.querySelector('[data-ajax-pagination-content]');
      const nextContent = nextRoot?.querySelector('[data-ajax-pagination-content]');
      if (!nextRoot || !currentContent || !nextContent) {
        window.location.assign(targetUrl.toString());
        return;
      }

      const itemsSelector = currentContent.dataset.ajaxItemsSelector || '';
      if (itemsSelector) {
        const availableSlots = currentContent.querySelectorAll(itemsSelector).length;
        const requiredSlots = nextContent.querySelectorAll(itemsSelector).length;
        if (requiredSlots > availableSlots) {
          window.location.assign(targetUrl.toString());
          return;
        }
      }

      morphPaginationNode(currentContent, nextContent);

      const currentHead = currentRoot.querySelector('[data-ajax-pagination-head]');
      const nextHead = nextRoot.querySelector('[data-ajax-pagination-head]');
      if (currentHead && nextHead) morphPaginationNode(currentHead, nextHead);

      const currentTabs = currentRoot.querySelector('[data-ajax-pagination-tabs]');
      const nextTabs = nextRoot.querySelector('[data-ajax-pagination-tabs]');
      if (currentTabs && nextTabs) morphPaginationNode(currentTabs, nextTabs);

      const currentSummary = currentRoot.querySelector('[data-ajax-pagination-summary]');
      const nextSummary = nextRoot.querySelector('[data-ajax-pagination-summary]');
      if (currentSummary && nextSummary) morphPaginationNode(currentSummary, nextSummary);

      const currentFilterForms = Array.from(currentRoot.querySelectorAll('[data-ajax-pagination-form]'));
      const nextFilterForms = Array.from(nextRoot.querySelectorAll('[data-ajax-pagination-form]'));
      currentFilterForms.forEach((filterForm, index) => {
        if (nextFilterForms[index]) morphPaginationNode(filterForm, nextFilterForms[index]);
      });

      const currentNavs = Array.from(currentRoot.querySelectorAll('[data-ajax-pagination-nav]'));
      const nextNavs = Array.from(nextRoot.querySelectorAll('[data-ajax-pagination-nav]'));
      currentNavs.forEach((nav, index) => {
        if (nextNavs[index]) nav.replaceWith(nextNavs[index].cloneNode(true));
        else nav.remove();
      });

      syncElementAttributes(currentRoot, nextRoot);

      if (push) window.history.pushState({ ajaxPagination: true, pageKey }, '', targetUrl);
      document.title = nextDocument.title || document.title;
      currentRoot.classList.remove('ajax-pagination-loading');
      currentRoot.removeAttribute('aria-busy');
      if (scroll) currentContent.scrollIntoView({ behavior: 'smooth', block: 'start' });
      document.dispatchEvent(new CustomEvent('crm:ajax-pagination-updated', {
        detail: { pageKey, url: targetUrl.toString(), content: currentContent },
      }));
      prefetchPaginationLinks(currentRoot);
    } catch (error) {
      if (error?.name === 'AbortError') return;
      window.location.assign(targetUrl.toString());
    } finally {
      currentRoot.classList.remove('ajax-pagination-loading');
      currentRoot.removeAttribute('aria-busy');
    }
  };

  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('[data-ajax-pagination-nav] a[href]');
    if (!link || link.target || link.hasAttribute('download')) return;
    const href = link.getAttribute('href') || '';
    if (!href || href === '#') return;
    const targetUrl = new URL(href, window.location.href);
    if (targetUrl.origin !== window.location.origin) return;
    const pageRoot = link.closest('[data-ajax-pagination-page]');
    event.preventDefault();
    updatePaginationPage(targetUrl, { root: pageRoot });
  });

  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('[data-ajax-pagination-tabs] .remarks-tab-link[href]');
    if (!link || link.target || link.hasAttribute('download')) return;
    const href = link.getAttribute('href') || '';
    if (!href || href === '#') return;
    const targetUrl = new URL(href, window.location.href);
    if (targetUrl.origin !== window.location.origin) return;

    const tabs = link.closest('[data-ajax-pagination-tabs]');
    const pageRoot = tabs?.closest('[data-ajax-pagination-page]');
    const pageKey = pageRoot?.dataset.ajaxPaginationPage || '';
    if (['glass-measurements', 'materials', 'developer-tools', 'site-errors'].includes(pageKey)
        && !document.documentElement.classList.contains('desktop-like-pointer')) return;
    event.preventDefault();
    tabs?.querySelectorAll('.remarks-tab-link').forEach(tab => tab.classList.toggle('active', tab === link));
    void updatePaginationPage(targetUrl, { push: true, scroll: false, useCache: false, root: pageRoot });
  });

  document.addEventListener('submit', event => {
    const form = event.target.closest('form[data-ajax-pagination-form]');
    if (!form || (form.method || 'get').toLowerCase() !== 'get') return;
    const pageRoot = form.closest('[data-ajax-pagination-page]');
    if (!pageRoot?.querySelector('[data-ajax-pagination-content]')) return;
    event.preventDefault();

    const targetUrl = new URL(form.action || window.location.href, window.location.href);
    targetUrl.search = '';
    const formData = new FormData(form);
    formData.forEach((value, key) => {
      const normalizedValue = String(value || '').trim();
      if (normalizedValue) targetUrl.searchParams.append(key, normalizedValue);
    });
    void updatePaginationPage(targetUrl, { push: true, scroll: false, useCache: false, root: pageRoot });
  });

  window.addEventListener('popstate', event => {
    const assignmentsRoot = document.querySelector('[data-ajax-pagination-page="assignments"]');
    if (assignmentsRoot) {
      const targetUrl = new URL(window.location.href);
      const targetView = targetUrl.searchParams.get('view') === 'issued' ? 'issued' : 'issue';
      const currentView = assignmentsRoot.dataset.assignmentView || 'issue';
      if (targetView !== currentView) return;
    }
    const pageKey = event.state?.pageKey || '';
    const pageRoot = pageKey
      ? document.querySelector(`[data-ajax-pagination-page="${CSS.escape(pageKey)}"]`)
      : document.querySelector('[data-ajax-pagination-page]');
    if (!pageRoot) return;
    updatePaginationPage(new URL(window.location.href), { push: false, root: pageRoot });
  });

  window.crmUpdatePaginationPage = (targetUrl, options = {}) => updatePaginationPage(targetUrl, options);

  const start = () => {
    const pageRoot = document.querySelector('[data-ajax-pagination-page]');
    if (pageRoot) prefetchPaginationLinks(pageRoot);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();

// Assignment view tabs keep the page chrome mounted and replace only the
// region between the markers immediately below the buttons. Mobile navigation
// remains the original full-page flow.
(() => {
  let assignmentTabRequest = null;

  const nodesBetween = (start, end) => {
    const nodes = [];
    let node = start?.nextSibling || null;
    while (node && node !== end) {
      nodes.push(node);
      node = node.nextSibling;
    }
    return nodes;
  };

  const assignmentViewForUrl = url => url.searchParams.get('view') === 'issued' ? 'issued' : 'issue';

  const loadAssignmentTab = async (targetUrl, pushHistory = true) => {
    const root = document.querySelector('[data-ajax-pagination-page="assignments"]');
    const currentStart = root?.querySelector('[data-assignment-tab-content-start]');
    const currentEnd = root?.querySelector('[data-assignment-tab-content-end]');
    const currentTabs = root?.querySelector('.assignment-subtabs');
    if (!root || !currentStart || !currentEnd || !currentTabs) {
      window.location.assign(targetUrl.toString());
      return false;
    }

    assignmentTabRequest?.abort();
    assignmentTabRequest = new AbortController();
    root.classList.add('ajax-pagination-loading');
    root.setAttribute('aria-busy', 'true');

    try {
      const response = await fetch(targetUrl.toString(), {
        credentials: 'same-origin',
        signal: assignmentTabRequest.signal,
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'X-CRM-Partial-Navigation': '1',
          'Accept': 'text/html',
        },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const sourceDocument = new DOMParser().parseFromString(await response.text(), 'text/html');
      const nextRoot = sourceDocument.querySelector('[data-ajax-pagination-page="assignments"]');
      const nextStart = nextRoot?.querySelector('[data-assignment-tab-content-start]');
      const nextEnd = nextRoot?.querySelector('[data-assignment-tab-content-end]');
      const nextTabs = nextRoot?.querySelector('.assignment-subtabs');
      if (!nextRoot || !nextStart || !nextEnd || !nextTabs) throw new Error('assignment partial region missing');

      const mountedAssigneeModal = document.querySelector('body > #assignmentChangeAssigneeModal');
      if (mountedAssigneeModal) {
        window.bootstrap?.Modal?.getInstance?.(mountedAssigneeModal)?.dispose();
        mountedAssigneeModal.remove();
      }

      nodesBetween(currentStart, currentEnd).forEach(node => node.remove());
      nodesBetween(nextStart, nextEnd).forEach(node => {
        currentEnd.before(document.importNode(node, true));
      });
      currentTabs.replaceChildren(...Array.from(nextTabs.childNodes, node => document.importNode(node, true)));
      root.dataset.assignmentView = nextRoot.dataset.assignmentView || assignmentViewForUrl(targetUrl);
      window.crmInitAssignmentChangeAssigneeModal?.();

      if (pushHistory) window.history.pushState({ assignmentTabs: true }, '', targetUrl);
      document.title = sourceDocument.title || document.title;
      document.dispatchEvent(new CustomEvent('crm:ajax-pagination-updated', {
        detail: { pageKey: 'assignments', url: targetUrl.toString(), content: root },
      }));
      return true;
    } catch (error) {
      if (error?.name === 'AbortError') return false;
      window.location.assign(targetUrl.toString());
      return false;
    } finally {
      root.classList.remove('ajax-pagination-loading');
      root.removeAttribute('aria-busy');
    }
  };

  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (!document.documentElement.classList.contains('desktop-like-pointer')) return;
    const link = event.target.closest('.assignment-subtabs .assignment-subtab[href]');
    if (!link || link.target || link.hasAttribute('download')) return;
    const root = link.closest('[data-ajax-pagination-page="assignments"]');
    if (!root) return;
    const targetUrl = new URL(link.href, window.location.href);
    if (targetUrl.origin !== window.location.origin) return;
    event.preventDefault();
    if (targetUrl.href === window.location.href) return;
    root.querySelectorAll('.assignment-subtab').forEach(tab => tab.classList.toggle('active', tab === link));
    void loadAssignmentTab(targetUrl, true);
  }, true);

  window.addEventListener('popstate', () => {
    if (!document.documentElement.classList.contains('desktop-like-pointer')) return;
    const root = document.querySelector('[data-ajax-pagination-page="assignments"]');
    if (!root) return;
    const targetUrl = new URL(window.location.href);
    const targetView = assignmentViewForUrl(targetUrl);
    const currentView = root.dataset.assignmentView || 'issue';
    if (targetView === currentView) return;
    void loadAssignmentTab(targetUrl, false);
  });
})();

// The pagination morph keeps compatible DOM nodes mounted, so a CSS entrance
// animation on a Measurements table would otherwise not restart when the user
// returns to the All tab. Replay one shared animation for every desktop tab.
document.addEventListener('crm:ajax-pagination-updated', event => {
  if (event.detail?.pageKey !== 'glass-measurements') return;
  if (!document.documentElement.classList.contains('desktop-like-pointer')) return;
  const shell = event.detail?.content?.querySelector?.('.glass-table-shell')
    || document.querySelector('[data-ajax-pagination-page="glass-measurements"] .glass-table-shell');
  if (!shell) return;
  shell.classList.remove('crm-tab-enter');
  void shell.offsetWidth;
  shell.classList.add('crm-tab-enter');
});

// Contractor names are also written into the status pill by quick actions.
// Rebuild the two-line desktop label after any such in-place update so the
// specialization never falls back to arbitrary word wrapping.
document.addEventListener('DOMContentLoaded', () => {
  const formatContractorStatusPill = pill => {
    if (!pill || pill.querySelector('.contractor-status-desktop')) return;
    const label = String(pill.textContent || '').replace(/\s+/g, ' ').trim();
    const match = label.match(/^(.+?)\s*(\([^()]+\))$/);
    if (!match) return;

    const desktopLabel = document.createElement('span');
    desktopLabel.className = 'contractor-status-desktop';
    desktopLabel.hidden = true;

    const nameLine = document.createElement('span');
    nameLine.className = 'contractor-status-line';
    nameLine.textContent = match[1].trim();

    const specializationLine = document.createElement('span');
    specializationLine.className = 'contractor-status-line';
    specializationLine.textContent = match[2];

    const defaultLabel = document.createElement('span');
    defaultLabel.className = 'contractor-status-default';
    defaultLabel.textContent = label;

    desktopLabel.append(nameLine, specializationLine);
    pill.replaceChildren(desktopLabel, defaultLabel);
    pill.classList.add('contractor-status-pill', 'has-contractor-break');
  };

  const formatContractorStatuses = scope => {
    if (!document.documentElement.classList.contains('desktop-like-pointer')) return;
    const pills = [];
    const selector = '.remarks-export-table-shell .task-table .task-status-cell .status-pill';
    if (scope?.matches?.(selector)) pills.push(scope);
    scope?.querySelectorAll?.(selector).forEach(pill => pills.push(pill));
    pills.forEach(formatContractorStatusPill);
  };

  const bindContractorStatusObservers = scope => {
    const tables = [];
    const selector = '.remarks-export-table-shell .task-table';
    if (scope?.matches?.(selector)) tables.push(scope);
    scope?.querySelectorAll?.(selector).forEach(table => tables.push(table));
    tables.forEach(table => {
      formatContractorStatuses(table);
      if (table.dataset.contractorStatusObserverBound === '1') return;
      let scheduled = false;
      const observer = new MutationObserver(() => {
        if (scheduled) return;
        scheduled = true;
        window.requestAnimationFrame(() => {
          scheduled = false;
          formatContractorStatuses(table);
        });
      });
      observer.observe(table, { childList: true, subtree: true, characterData: true });
      table.dataset.contractorStatusObserverBound = '1';
    });
  };

  bindContractorStatusObservers(document);
  document.addEventListener('crm:ajax-pagination-updated', event => {
    bindContractorStatusObservers(event.detail?.content || document);
  });
});

document.addEventListener('click', event => {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  if (!document.documentElement.classList.contains('desktop-like-pointer')) return;
  const link = event.target.closest('.developer-stat-summary-link[href]');
  if (!link || link.target || link.hasAttribute('download')) return;
  const root = link.closest('[data-ajax-pagination-page="developer-statistics"]');
  if (!root || typeof window.crmUpdatePaginationPage !== 'function') return;
  const targetUrl = new URL(link.href, window.location.href);
  if (targetUrl.origin !== window.location.origin) return;
  event.preventDefault();
  root.querySelectorAll('.developer-stat-summary-link').forEach(card => {
    const isActive = card === link;
    card.classList.toggle('is-active', isActive);
    if (isActive) card.setAttribute('aria-current', 'page');
    else card.removeAttribute('aria-current');
  });
  void window.crmUpdatePaginationPage(targetUrl, {
    push: true,
    scroll: false,
    useCache: false,
    root,
  });
});

document.addEventListener('click', event => {
  const button = event.target.closest('.site-error-delete-trigger');
  if (!button) return;
  const form = document.getElementById('deleteErrorForm');
  const text = document.getElementById('deleteErrorText');
  if (!form) return;
  form.action = button.dataset.deleteUrl || '';
  const title = button.dataset.errorTitle || 'эту ошибку';
  if (text) text.textContent = `Удалить запись: ${title}? Это действие нельзя отменить.`;
});

document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('[data-contractor-response-autosave]');
  if (!form || !document.documentElement.classList.contains('desktop-like-pointer')) return;

  const saveState = form.querySelector('[data-contractor-response-save-state]');
  const saveStateIcon = saveState?.querySelector('i');
  const saveStateText = saveState?.querySelector('span');
  const setSaveState = (mode, message) => {
    if (!saveState) return;
    saveState.classList.remove('is-saving', 'is-saved', 'is-error');
    if (mode) saveState.classList.add(`is-${mode}`);
    if (saveStateText) saveStateText.textContent = message;
    if (saveStateIcon) {
      saveStateIcon.className = mode === 'saving'
        ? 'bi bi-arrow-repeat'
        : mode === 'error'
          ? 'bi bi-exclamation-circle'
          : 'bi bi-cloud-check';
    }
  };

  form.querySelectorAll('input[type="radio"][data-contractor-id]').forEach(input => {
    input.dataset.saved = input.checked ? '1' : '0';
  });

  form.addEventListener('submit', event => event.preventDefault());
  form.addEventListener('change', async event => {
    const input = event.target.closest?.('input[type="radio"][data-contractor-id]');
    if (!input || !input.checked) return;

    const card = input.closest('.contractor-response-card');
    const options = input.closest('.contractor-response-options');
    const radios = Array.from(options?.querySelectorAll('input[type="radio"]') || []);
    const previouslySaved = radios.find(radio => radio.dataset.saved === '1');
    const body = new FormData();
    body.set('csrf_token', form.querySelector('input[name="csrf_token"]')?.value || '');
    body.set('contractor_id', input.dataset.contractorId || '');
    body.set('status', input.value);

    radios.forEach(radio => { radio.disabled = true; });
    card?.classList.add('is-saving');
    card?.setAttribute('aria-busy', 'true');
    setSaveState('saving', 'Сохраняем статус…');

    try {
      const response = await fetch(form.action || window.location.href, {
        method: 'POST',
        body,
        credentials: 'same-origin',
        headers: {
          'Accept': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.ok) {
        throw new Error(data?.message || 'Не удалось сохранить статус подрядчика.');
      }
      radios.forEach(radio => {
        radio.dataset.saved = radio === input ? '1' : '0';
      });
      setSaveState('saved', 'Статус сохранён автоматически');
    } catch (error) {
      if (previouslySaved) previouslySaved.checked = true;
      setSaveState('error', 'Не удалось сохранить статус');
      window.showCrmNotice?.(error.message || 'Не удалось сохранить статус подрядчика.', 'danger');
    } finally {
      radios.forEach(radio => { radio.disabled = false; });
      card?.classList.remove('is-saving');
      card?.removeAttribute('aria-busy');
    }
  });
});

// Issued-day filters update only their own content. The fixed mobile header
// and bottom navigation stay mounted, so changing Today/Tomorrow does not
// replay the full-page entry animation or make the shell jump.
document.addEventListener('DOMContentLoaded', () => {
  let issuedFilterRequest = null;

  const replaceIssuedRegion = (sourceDocument, targetUrl, pushHistory = true) => {
    const nextFilters = sourceDocument.querySelector('.assignment-issued-filters');
    const nextLayout = sourceDocument.querySelector('.assignment-issued-layout');
    const currentFilters = document.querySelector('.assignment-issued-filters');
    const currentLayout = document.querySelector('.assignment-issued-layout');
    if (!nextFilters || !nextLayout || !currentFilters || !currentLayout) return false;

    currentFilters.replaceWith(nextFilters);
    currentLayout.replaceWith(nextLayout);

    const nextAssigneeForm = sourceDocument.querySelector('#assignmentChangeAssigneeModal form');
    const currentAssigneeForm = document.querySelector('#assignmentChangeAssigneeModal form');
    if (nextAssigneeForm && currentAssigneeForm) {
      currentAssigneeForm.action = nextAssigneeForm.action;
    }

    const nextIssuedSubtab = sourceDocument.querySelector('.assignment-subtab[href*="view=issued"]');
    const currentIssuedSubtab = document.querySelector('.assignment-subtab[href*="view=issued"]');
    if (nextIssuedSubtab && currentIssuedSubtab) currentIssuedSubtab.innerHTML = nextIssuedSubtab.innerHTML;
    if (pushHistory) window.history.pushState({ assignmentIssuedFilter: true }, '', targetUrl);
    return true;
  };

  const loadIssuedFilter = async (url, pushHistory = true) => {
    if (!url) return false;
    issuedFilterRequest?.abort();
    issuedFilterRequest = new AbortController();

    const filters = document.querySelector('.assignment-issued-filters');
    filters?.classList.add('is-updating');
    filters?.setAttribute('aria-busy', 'true');

    try {
      const response = await fetch(url, {
        credentials: 'same-origin',
        signal: issuedFilterRequest.signal,
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'text/html',
        },
      });
      if (!response.ok) throw new Error('Не удалось обновить список задач');
      const html = await response.text();
      const sourceDocument = new DOMParser().parseFromString(html, 'text/html');
      if (!replaceIssuedRegion(sourceDocument, url, pushHistory)) {
        throw new Error('Не удалось обновить список задач');
      }
      return true;
    } catch (error) {
      if (error.name === 'AbortError') return false;
      showCrmNotice(error.message || 'Не удалось обновить список задач', 'danger');
      return false;
    } finally {
      const activeFilters = document.querySelector('.assignment-issued-filters');
      activeFilters?.classList.remove('is-updating');
      activeFilters?.removeAttribute('aria-busy');
    }
  };

  window.crmRefreshIssuedAssignments = () => loadIssuedFilter(window.location.href, false);

  document.addEventListener('click', event => {
    const link = event.target.closest('.js-assignment-issued-filter');
    if (!link || event.defaultPrevented) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();

    const filters = link.closest('.assignment-issued-filters');
    filters?.querySelectorAll('.assignment-filter-pill').forEach(item => item.classList.remove('active'));
    link.classList.add('active');
    void loadIssuedFilter(link.href, true);
  }, true);

  window.addEventListener('popstate', () => {
    if (!document.querySelector('.assignment-issued-filters')) return;
    void loadIssuedFilter(window.location.href, false);
  });
});

// iOS can keep a :hover/focus state after the first tap on fixed navigation.
// Commit a short touch gesture on pointerup so one deliberate tap always
// navigates, while a drag/scroll gesture is ignored.
document.addEventListener('DOMContentLoaded', () => {
  let mobileNavGesture = null;

  document.addEventListener('pointerdown', event => {
    const link = event.target.closest('.mobile-bottom-nav .mobile-nav-item[href]');
    if (!link || event.button !== 0) return;
    const targetUrl = new URL(link.href, window.location.href);
    const currentUrl = new URL(window.location.href);
    if (targetUrl.href === currentUrl.href) return;
    if (event.pointerType !== 'touch') return;
    mobileNavGesture = {
      link,
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      startedAt: Date.now(),
    };
  }, { passive: true, capture: true });

  document.addEventListener('pointercancel', () => {
    mobileNavGesture = null;
  }, { passive: true, capture: true });

  document.addEventListener('pointerup', event => {
    const gesture = mobileNavGesture;
    mobileNavGesture = null;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const moved = Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y);
    const heldFor = Date.now() - gesture.startedAt;
    if (moved > 12 || heldFor > 700) return;

    const targetUrl = new URL(gesture.link.href, window.location.href);
    const currentUrl = new URL(window.location.href);
    if (targetUrl.href === currentUrl.href) return;
    event.preventDefault();
    event.stopPropagation();
    gesture.link.dataset.touchNavigationCommitted = '1';
    rememberInstantMobileEntryForNextNavigation(targetUrl.href);
    window.location.assign(targetUrl.href);
  }, { passive: false, capture: true });

  document.addEventListener('click', event => {
    const link = event.target.closest('.mobile-bottom-nav .mobile-nav-item[href]');
    if (!link || link.dataset.touchNavigationCommitted === '1') return;
    const targetUrl = new URL(link.href, window.location.href);
    if (targetUrl.href === window.location.href) return;
    rememberInstantMobileEntryForNextNavigation(targetUrl.href);
  }, true);

  document.addEventListener('click', event => {
    const link = event.target.closest('.mobile-bottom-nav .mobile-nav-item[data-touch-navigation-committed="1"]');
    if (!link) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
  }, true);
});

// Mobile adaptation helpers
// Keeps the desktop markup intact, but makes navigation, tables and task rows usable on phones.
document.addEventListener('DOMContentLoaded', () => {
  const body = document.body;
  const menuToggles = Array.from(document.querySelectorAll('.mobile-menu-toggle'));
  const menuToggle = menuToggles[0] || null;
  const sidebar = document.querySelector('.app-sidebar');
  const sidebarBackdrop = document.querySelector('.mobile-sidebar-backdrop');

  const closeMobileMenu = () => {
    body.classList.remove('mobile-menu-open');
    menuToggles.forEach(toggle => toggle.setAttribute('aria-expanded', 'false'));
  };

  const openMobileMenu = () => {
    body.classList.add('mobile-menu-open');
    menuToggles.forEach(toggle => toggle.setAttribute('aria-expanded', 'true'));
  };

  if (menuToggles.length && sidebar) {
    menuToggles.forEach(toggle => {
      toggle.addEventListener('click', () => {
        if (body.classList.contains('mobile-menu-open')) {
          closeMobileMenu();
        } else {
          openMobileMenu();
        }
      });
    });
  }

  if (sidebarBackdrop) {
    sidebarBackdrop.addEventListener('click', closeMobileMenu);
  }

  if (sidebar) {
    sidebar.querySelectorAll('a.sidebar-link, a.sidebar-sublink').forEach(link => {
      link.addEventListener('click', closeMobileMenu);
    });
  }

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeMobileMenu();
  });

  // Convert wide tables to mobile cards only on true mobile viewports.
  const syncResponsiveTableCards = (scope = document) => {
    const useMobileCards = isMobileViewport();

    scope.querySelectorAll('.table').forEach(table => {
      if (table.classList.contains('material-edit-table')) return;
      if (table.closest('.desktop-only-table')) return;

      const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.textContent.trim());
      if (!headers.length) return;

      table.classList.toggle('mobile-card-table', useMobileCards);
      if (!useMobileCards || table.dataset.mobileLabelsReady === '1') return;
      table.querySelectorAll('tbody tr').forEach(row => {
        Array.from(row.children).forEach((cell, index) => {
          if (!cell.dataset.label && headers[index]) {
            cell.dataset.label = headers[index];
          }
        });
      });
      table.dataset.mobileLabelsReady = '1';
    });
  };

  syncResponsiveTableCards();
  let responsiveTableMode = isMobileViewport();
  const syncResponsiveTablesOnModeChange = () => {
    const nextMode = isMobileViewport();
    if (nextMode === responsiveTableMode) return;
    responsiveTableMode = nextMode;
    syncResponsiveTableCards();
  };
  window.addEventListener('resize', syncResponsiveTablesOnModeChange, { passive: true });
  document.addEventListener('crm:ajax-pagination-updated', event => {
    syncResponsiveTableCards(event.detail?.content || document);
  });

  // Карточка замечания/подрядчика открывается двойным нажатием по строке.
});


// Inline material request title editing
document.addEventListener('click', function (event) {
  const toggle = event.target.closest('.material-title-edit-toggle');
  if (toggle) {
    const target = document.getElementById(toggle.dataset.target);
    if (target) {
      target.classList.remove('d-none');
      target.querySelector('input')?.focus();
    }
    return;
  }
  const cancel = event.target.closest('.material-title-cancel');
  if (cancel) {
    const form = cancel.closest('.material-rename-form');
    if (form) {
      form.classList.add('d-none');
      const input = form.querySelector('input[name="title"]');
      if (input) input.value = input.defaultValue;
    }
  }
});

// CRM polish: numeric-only inputs, row checkbox toggle, styled confirmations and safe download buttons.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-digits-only="1"]').forEach(input => {
    const clean = () => { input.value = (input.value || '').replace(/\D+/g, ''); };
    input.addEventListener('input', clean);
    input.addEventListener('paste', () => setTimeout(clean, 0));
  });

  const initMaterialSelectRows = (scope = document) => {
    const rows = [];
    if (scope.matches?.('.material-select-row')) rows.push(scope);
    scope.querySelectorAll?.('.material-select-row').forEach(row => rows.push(row));
    rows.forEach(row => {
      if (row.dataset.materialSelectBound === '1') return;
      const checkbox = row.querySelector('input[type="checkbox"]');
      const syncState = () => row.classList.toggle('is-selected', Boolean(checkbox?.checked));
      row.addEventListener('click', event => {
        if (event.target.closest('textarea, select')) return;
        if (!checkbox) return;
        if (!event.target.closest('input[type="checkbox"]')) {
          checkbox.checked = !checkbox.checked;
          checkbox.dispatchEvent(new Event('change', { bubbles: true }));
        }
        syncState();
      });
      row.addEventListener('dblclick', event => {
        if (event.target.closest('a, button, form, input, textarea, select, label')) return;
        const href = row.dataset.href;
        if (href) window.location.href = href;
      });
      if (checkbox) {
        checkbox.addEventListener('change', syncState);
        syncState();
      }
      row.dataset.materialSelectBound = '1';
    });
  };

  const initMaterialWriteoffForms = (scope = document) => {
    const forms = [];
    if (scope.matches?.('.js-material-writeoff-form')) forms.push(scope);
    scope.querySelectorAll?.('.js-material-writeoff-form').forEach(form => forms.push(form));
    forms.forEach(form => {
    if (form.dataset.materialWriteoffBound === '1') return;
    form.dataset.materialWriteoffBound = '1';
    const storageKey = form.dataset.selectionKey || 'material-writeoff-selection';
    const hiddenBox = form.querySelector('.js-material-selected-hidden');
    const countEl = form.querySelector('.js-material-selected-count');
    const clearBtn = form.querySelector('.js-material-selected-clear');
    const selectedStrip = form.querySelector('.js-material-selected-strip');
    const noPersistSelection = form.dataset.noPersistSelection === '1';
    let transientSelection = new Set();

    if (noPersistSelection) {
      try { localStorage.removeItem(storageKey); } catch (error) {}
    }

    const readSelection = () => {
      if (noPersistSelection) return new Set(transientSelection);
      try {
        return new Set(JSON.parse(localStorage.getItem(storageKey) || '[]').map(String));
      } catch (error) {
        return new Set();
      }
    };
    const writeSelection = (selection) => {
      if (noPersistSelection) {
        transientSelection = new Set(selection);
        return;
      }
      localStorage.setItem(storageKey, JSON.stringify(Array.from(selection)));
    };
    const clearSelection = () => {
      transientSelection = new Set();
      try { localStorage.removeItem(storageKey); } catch (error) {}
    };
    const syncSelectionUi = () => {
      const selection = readSelection();
      form.querySelectorAll('.material-task-check').forEach(check => {
        check.checked = selection.has(String(check.value));
        check.closest('.material-select-row')?.classList.toggle('is-selected', check.checked);
      });
      if (countEl) countEl.textContent = String(selection.size);
      if (selectedStrip) selectedStrip.classList.toggle('d-none', selection.size === 0);
      if (hiddenBox) {
        hiddenBox.innerHTML = '';
        selection.forEach(taskId => {
          const hidden = document.createElement('input');
          hidden.type = 'hidden';
          hidden.name = 'task_ids';
          hidden.value = taskId;
          hiddenBox.appendChild(hidden);
        });
      }
    };

    const bindSelectionChecks = (scope = form) => {
      scope.querySelectorAll('.material-task-check').forEach(check => {
        if (check.dataset.writeoffSelectionBound === '1') return;
        check.addEventListener('change', () => {
          const selection = readSelection();
          if (check.checked) selection.add(String(check.value));
          else selection.delete(String(check.value));
          writeSelection(selection);
          syncSelectionUi();
        });
        check.dataset.writeoffSelectionBound = '1';
      });
    };

    bindSelectionChecks();

    const parseWriteoffNumber = value => {
      const normalized = String(value || '').replace(/[\s\u00a0]+/g, '').replace(',', '.');
      const number = Number(normalized);
      return Number.isFinite(number) ? number : NaN;
    };
    const formatWriteoffNumber = value => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 }).format(value);
    const validateWriteoffBalances = () => {
      const totals = new Map();
      for (const line of form.querySelectorAll('.js-material-line')) {
        const select = line.querySelector('.js-writeoff-material-select');
        const input = line.querySelector('.js-writeoff-quantity-input');
        if (!select?.value && !input?.value.trim()) continue;
        const option = select?.selectedOptions?.[0];
        if (!select?.value) return { input: select, message: 'Выберите материал для списания.' };
        const quantity = parseWriteoffNumber(input?.value);
        if (!Number.isFinite(quantity) || quantity <= 0) {
          return { input, message: 'Введите корректное количество материала больше нуля.' };
        }
        const balance = parseWriteoffNumber(option?.dataset?.balance);
        const [name = option?.textContent?.trim() || 'Материал', unit = ''] = String(select.value).split('|||');
        const current = totals.get(select.value) || { name, unit, balance, quantity: 0, input };
        current.quantity += quantity;
        totals.set(select.value, current);
      }
      for (const row of totals.values()) {
        if (Number.isFinite(row.balance) && row.quantity > row.balance + 0.000001) {
          const unitSuffix = row.unit ? ` ${row.unit}` : '';
          return {
            input: row.input,
            message: `Для материала «${row.name}» введено ${formatWriteoffNumber(row.quantity)}${unitSuffix}, доступно только ${formatWriteoffNumber(row.balance)}${unitSuffix}. Уменьшите количество.`,
          };
        }
      }
      return null;
    };

    clearBtn?.addEventListener('click', () => {
      clearSelection();
      syncSelectionUi();
    });

    form.addEventListener('submit', () => {
      syncSelectionUi();
    });

    if (document.documentElement.classList.contains('desktop-like-pointer')) {
      form.addEventListener('submit', async event => {
        event.preventDefault();
        if (form.dataset.writeoffSubmitting === '1') return;

        syncSelectionUi();
        if (readSelection().size === 0) {
          showCrmNotice('Выберите хотя бы одно замечание для списания.', 'danger');
          return;
        }
        const balanceError = validateWriteoffBalances();
        if (balanceError) {
          balanceError.input?.classList.add('is-invalid');
          balanceError.input?.focus({ preventScroll: true });
          showCrmNotice(balanceError.message, 'danger');
          return;
        }
        const submitter = event.submitter;
        const formData = new FormData(form);
        if (submitter?.name) formData.set(submitter.name, submitter.value);
        const previousHtml = submitter?.innerHTML || '';
        form.dataset.writeoffSubmitting = '1';
        form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = true; });
        if (submitter) {
          submitter.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Сохраняю';
        }

        try {
          const submitUrl = form.dataset.submitUrl || form.getAttribute('action') || window.location.href;
          const response = await fetch(new URL(submitUrl, document.baseURI).toString(), {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
              'Accept': 'application/json',
            },
          });
          const responseText = await response.text();
          let data = {};
          try {
            data = responseText ? JSON.parse(responseText) : {};
          } catch (parseError) {
            const responseDocument = new DOMParser().parseFromString(responseText, 'text/html');
            const serverMessage = responseDocument.querySelector('.crm-toast-text, main .alert, h1')?.textContent?.trim();
            data = { ok: false, message: serverMessage || '' };
          }
          if (!response.ok || data.ok === false) {
            const statusMessages = {
              400: 'Сервер отклонил введённые данные. Проверьте выбранный материал и количество.',
              403: 'Недостаточно прав для списания материала.',
              409: 'Остаток или выбранное замечание уже изменились. Обновите данные и повторите попытку.',
              429: 'Слишком много попыток. Подождите минуту и повторите списание.',
              500: 'Внутренняя ошибка сервера при списании материала.',
            };
            const error = new Error(data.message || statusMessages[response.status] || `Ошибка списания: сервер вернул код ${response.status}.`);
            error.field = data.field || '';
            throw error;
          }
          showCrmNotice(data.message || 'Материал списан', 'success');
          if (data.redirect_url) window.location.assign(data.redirect_url);
        } catch (error) {
          if (error.field === 'quantity') {
            const quantityInput = form.querySelector('.js-writeoff-quantity-input');
            quantityInput?.classList.add('is-invalid');
            quantityInput?.focus({ preventScroll: true });
          }
          const errorMessage = error?.name === 'TypeError'
            ? 'Сервер не ответил. Проверьте подключение к интернету и повторите попытку.'
            : (error.message || 'Не удалось списать материал: сервер не сообщил причину.');
          showCrmNotice(errorMessage, 'danger');
        } finally {
          delete form.dataset.writeoffSubmitting;
          form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = false; });
          if (submitter) submitter.innerHTML = previousHtml;
        }
      });
    }

    if (noPersistSelection) {
      window.addEventListener('pagehide', clearSelection, { once: true });
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') clearSelection();
      });
    }

    syncSelectionUi();
    });
  };

  initMaterialSelectRows();
  initMaterialWriteoffForms();
  document.addEventListener('crm:ajax-pagination-updated', event => {
    if (event.detail?.pageKey !== 'materials') return;
    const content = event.detail?.content || document;
    initMaterialSelectRows(content);
    initMaterialWriteoffForms(content);
  });


  const updateGlassBulkAction = () => {
    const actions = document.querySelectorAll('.js-glass-bulk-action');
    if (!actions.length) return;
    const hasChecked = Array.from(document.querySelectorAll('.glass-order-check')).some(check => check.checked && !check.disabled);
    actions.forEach(action => action.classList.toggle('d-none', !hasChecked));
  };

  document.querySelectorAll('.glass-order-check').forEach(check => {
    check.addEventListener('change', updateGlassBulkAction);
  });

  document.querySelectorAll('.glass-order-row:not(.js-bulk-row)').forEach(row => {
    const checkbox = row.querySelector('.glass-order-check');
    const syncState = () => row.classList.toggle('is-selected', Boolean(checkbox?.checked));
    row.addEventListener('click', event => {
      if (event.target.closest('a, button, form, textarea, select, label')) return;
      if (!checkbox || checkbox.disabled) return;
      if (!event.target.closest('input[type="checkbox"]')) {
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
      }
      syncState();
      updateGlassBulkAction();
    });
    if (checkbox) {
      checkbox.addEventListener('change', () => { syncState(); updateGlassBulkAction(); });
      syncState();
    }
  });
  updateGlassBulkAction();

  const initStandaloneWriteoffSelects = (scope = document) => {
    const selects = [];
    if (scope.matches?.('.js-writeoff-material-select')) selects.push(scope);
    scope.querySelectorAll?.('.js-writeoff-material-select').forEach(select => selects.push(select));
    selects.forEach(select => {
    if (select.closest('.js-material-line') || select.dataset.writeoffQuantityBound === '1') return;
    select.dataset.writeoffQuantityBound = '1';
    const form = select.closest('form');
    const block = form?.querySelector('.js-writeoff-quantity-block');
    const input = block?.querySelector('.js-writeoff-quantity-input');
    const unitBadge = block?.querySelector('.js-writeoff-unit-badge');
    const balanceHint = block?.querySelector('.js-writeoff-balance-hint');
    const syncWriteoffQuantity = () => {
      const option = select.selectedOptions && select.selectedOptions[0];
      const unit = option?.dataset?.unit || '';
      const balance = option?.dataset?.balance || '';
      const hasMaterial = Boolean(select.value);
      block?.classList.toggle('d-none', !hasMaterial);
      if (input) {
        input.disabled = !hasMaterial;
        input.placeholder = unit ? `Введите количество, ${unit}` : 'Введите количество';
      }
      if (unitBadge) unitBadge.textContent = unit ? `ед. изм: ${unit}` : '';
      if (balanceHint) balanceHint.textContent = hasMaterial && balance ? `Доступно к списанию: ${balance} ${unit}` : '';
      if (!hasMaterial && input) {
        input.value = '';
        input.classList.remove('is-invalid');
      }
    };
    select.addEventListener('change', syncWriteoffQuantity);
    syncWriteoffQuantity();
    });
  };

  initStandaloneWriteoffSelects();
  document.addEventListener('crm:ajax-pagination-updated', event => {
    if (event.detail?.pageKey === 'materials') {
      initStandaloneWriteoffSelects(event.detail?.content || document);
    }
  });

  const excelNoticeText = 'Ожидайте генерации таблицы Excel. Как только файл будет подготовлен, автоматически начнется скачивание.';
  const excelReadyNoticeText = 'Таблица Excel готова. Скачивание уже началось.';

  const buildLoadingDotsMarkup = trigger => {
    const loadingText = trigger?.dataset?.loadingText || 'Готовим Excel';
    return `
      <span class="crm-loading-inline" aria-hidden="true">
        <span class="crm-loading-inline-text">${escapeHtml(loadingText)}</span>
        <span class="crm-loading-dots">
          <span></span>
          <span></span>
          <span></span>
        </span>
      </span>
    `;
  };

  const showExcelGenerationNotice = trigger => {
    if (!trigger) return;
    trigger.dataset.excelNoticeShown = '1';
  };

  const clearExcelGenerationNotice = trigger => {
    if (!trigger) return;
    delete trigger.dataset.excelNoticeShown;
  };

  const showExcelReadyNotice = trigger => {
    if (!trigger || trigger.dataset.excelReadyNoticeShown === '1') return;
    trigger.dataset.excelReadyNoticeShown = '1';
    showCrmNotice(excelReadyNoticeText, 'success');
    window.setTimeout(() => {
      if (trigger) delete trigger.dataset.excelReadyNoticeShown;
    }, 2200);
  };

  const bindStatisticsTopCard = ({ selector, currentPageSelector, datasetKey, requestTop = null }) => {
    document.querySelectorAll(selector).forEach(card => {
      const rawHref = card.getAttribute('href') || '';
      const targetUrl = rawHref ? rawHref.replace(/#.*$/, '') : '';
      if (targetUrl) {
        card.dataset[datasetKey] = targetUrl;
        if (card.tagName === 'A') card.setAttribute('href', targetUrl);
      }
      card.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        if (typeof requestTop === 'function') requestTop();
        clearRememberedScrollPosition();

        if (document.body.classList.contains('app-body') && document.querySelector(currentPageSelector)) {
        if (window.location.hash) {
          history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
        }
        writePageScrollPosition(0, 0);
        return;
      }

        const nextUrl = card.dataset[datasetKey] || targetUrl;
        if (nextUrl) {
          window.location.assign(nextUrl);
        }
      }, true);
      card.addEventListener('keydown', event => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        card.click();
      });
    });
  };

  const startNativeExcelDownload = link => {
    if (!link?.href) return;
    const iframe = document.createElement('iframe');
    iframe.hidden = true;
    iframe.setAttribute('aria-hidden', 'true');
    iframe.className = 'js-excel-download-frame';
    iframe.src = `${link.href}${link.href.includes('?') ? '&' : '?'}download_ts=${Date.now()}`;
    document.body.appendChild(iframe);
    window.setTimeout(() => iframe.remove(), 45000);
  };

  const closeExcelDropdown = trigger => {
    const menu = trigger?.closest('.dropdown-menu');
    if (!menu) return;
    const dropdown = menu.closest('.dropdown');
    const toggle = dropdown?.querySelector('[data-bs-toggle="dropdown"]');
    if (toggle && window.bootstrap?.Dropdown) {
      const dropdownInstance = window.bootstrap.Dropdown.getInstance(toggle) || new window.bootstrap.Dropdown(toggle);
      dropdownInstance.hide();
      return;
    }
    menu.classList.remove('show');
    dropdown?.classList.remove('show');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  };

  const trySetBusyState = trigger => {
    if (!trigger) return false;
    try {
      setBusyState(trigger);
      return true;
    } catch (error) {
      try {
        const originalHtml = trigger.dataset.originalHtml || trigger.innerHTML;
        trigger.dataset.originalHtml = originalHtml;
        trigger.classList.add('disabled');
        trigger.classList.add('is-loading');
        if ('disabled' in trigger) trigger.disabled = true;
      } catch (noopError) {
        return false;
      }
      return false;
    }
  };

  const startNativeExcelDownloadFlow = link => {
    if (!link) return;
    let temporaryBusyApplied = false;
    try {
      setTemporaryBusyState(link, 2600);
      temporaryBusyApplied = true;
    } catch (error) {
      trySetBusyState(link);
      window.setTimeout(() => {
        showExcelReadyNotice(link);
        restoreBusyState(link);
      }, 2200);
    }
    startNativeExcelDownload(link);
    if (!temporaryBusyApplied) {
      window.setTimeout(() => restoreBusyState(link), 2800);
    }
  };

  const setTemporaryBusyState = (trigger, delay = 2200) => {
    if (!trigger) return;
    const originalHtml = trigger.dataset.originalHtml || trigger.innerHTML;
    trigger.dataset.originalHtml = originalHtml;
    showExcelGenerationNotice(trigger);
    trigger.classList.add('disabled');
    trigger.classList.add('is-loading');
    if ('disabled' in trigger) trigger.disabled = true;
    trigger.innerHTML = buildLoadingDotsMarkup(trigger);
    window.setTimeout(() => {
      showExcelReadyNotice(trigger);
    }, Math.min(delay, 900));
    window.setTimeout(() => {
      trigger.innerHTML = originalHtml;
      trigger.classList.remove('disabled');
      trigger.classList.remove('is-loading');
      if ('disabled' in trigger) trigger.disabled = false;
      clearExcelGenerationNotice(trigger);
    }, delay);
  };

  const restoreBusyState = trigger => {
    if (!trigger || !trigger.dataset.originalHtml) return;
    trigger.innerHTML = trigger.dataset.originalHtml;
    trigger.classList.remove('disabled');
    trigger.classList.remove('is-loading');
    if ('disabled' in trigger) trigger.disabled = false;
    clearExcelGenerationNotice(trigger);
  };

  const setBusyState = trigger => {
    if (!trigger) return;
    const originalHtml = trigger.dataset.originalHtml || trigger.innerHTML;
    trigger.dataset.originalHtml = originalHtml;
    showExcelGenerationNotice(trigger);
    trigger.classList.add('disabled');
    trigger.classList.add('is-loading');
    if ('disabled' in trigger) trigger.disabled = true;
    trigger.innerHTML = buildLoadingDotsMarkup(trigger);
  };

  const triggerBlobDownload = (blob, filename) => {
    const objectUrl = window.URL.createObjectURL(blob);
    const tempLink = document.createElement('a');
    tempLink.href = objectUrl;
    tempLink.download = filename || 'export.xlsx';
    tempLink.style.display = 'none';
    document.body.appendChild(tempLink);
    tempLink.click();
    tempLink.remove();
    window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
  };

  const getDownloadFilename = response => {
    const header = response.headers.get('Content-Disposition') || '';
    const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match && utf8Match[1]) return decodeURIComponent(utf8Match[1]);
    const basicMatch = header.match(/filename=\"?([^\";]+)\"?/i);
    if (basicMatch && basicMatch[1]) return basicMatch[1];
    try {
      const url = new URL(response.url, window.location.origin);
      const candidate = url.pathname.split('/').pop();
      return candidate || 'export.xlsx';
    } catch (error) {
      return 'export.xlsx';
    }
  };

  document.querySelectorAll('.download-excel-btn').forEach(link => {
    link.addEventListener('click', async event => {
      if (event.defaultPrevented) return;
      if (event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (link.classList.contains('is-loading')) return;
      event.preventDefault();
      const isDropdownDownload = !!link.closest('.dropdown-menu');
      const useFetchDownload = !isDropdownDownload || link.dataset.downloadMode === 'fetch';
      if (!useFetchDownload || typeof window.fetch !== 'function') {
        startNativeExcelDownloadFlow(link);
        return;
      }
      if (isDropdownDownload) event.stopPropagation();
      trySetBusyState(link);
      try {
        const response = await window.fetch(link.href, {
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel, application/octet-stream, application/json;q=0.9, */*;q=0.8'
          }
        });
        const contentType = (response.headers.get('Content-Type') || '').toLowerCase();
        const contentDisposition = response.headers.get('Content-Disposition') || '';
        if (contentType.includes('application/json')) {
          const payload = await response.json().catch(() => null);
          if (!response.ok || payload?.ok === false) {
            throw new Error(payload?.message || 'Не удалось подготовить Excel.');
          }
        } else if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const looksLikeDownload = /attachment/i.test(contentDisposition)
          || contentType.includes('spreadsheet')
          || contentType.includes('application/vnd.ms-excel')
          || contentType.includes('application/octet-stream');
        if (!looksLikeDownload) {
          window.location.href = link.href;
          return;
        }
        const blob = await response.blob();
        triggerBlobDownload(blob, getDownloadFilename(response));
        showExcelReadyNotice(link);
        if (isDropdownDownload) {
          window.setTimeout(() => closeExcelDropdown(link), 360);
        }
      } catch (error) {
        const message = error instanceof Error && error.message && !/^HTTP \d+$/.test(error.message)
          ? error.message
          : 'Не удалось подготовить Excel. Попробуйте еще раз.';
        showCrmNotice(message, 'warning');
      } finally {
        restoreBusyState(link);
      }
    });
  });

  document.querySelectorAll('.js-background-download-link').forEach(link => {
    link.addEventListener('click', async event => {
      if (event.defaultPrevented) return;
      if (event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (link.classList.contains('is-loading')) return;
      event.preventDefault();
      startNativeExcelDownloadFlow(link);
    });
  });

  const ensureConfirmModal = () => {
    let modal = document.querySelector('.js-crm-confirm-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'crm-confirm-overlay js-crm-confirm-modal d-none';
    modal.innerHTML = `
      <div class="crm-confirm-card" role="dialog" aria-modal="true">
        <div class="confirm-modal-icon"><i class="bi bi-exclamation-triangle"></i></div>
        <h2>Подтвердите действие</h2>
        <p class="js-crm-confirm-text">Удалить запись?</p>
        <div class="modal-actions">
          <button class="btn btn-danger js-crm-confirm-ok" type="button">Удалить</button>
          <button class="btn btn-outline-secondary js-crm-confirm-cancel" type="button">Отмена</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    return modal;
  };

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.classList.contains('assignment-remove-user-form')) return;
    const submitter = event.submitter
      || (form.classList.contains('material-writeoff-delete-form')
        ? form.querySelector('.material-writeoff-delete-btn')
        : null);
    const confirmText = normalizeConfirmText(submitter?.dataset?.confirmResolved || submitter?.dataset?.confirm || form.dataset.confirm);
    if (!confirmText || form.dataset.confirmed === '1') return;
    event.preventDefault();
    const modal = ensureConfirmModal();
    modal.querySelector('.js-crm-confirm-text').textContent = confirmText || 'Подтвердите действие';
    modal.classList.remove('d-none');
    const cancel = modal.querySelector('.js-crm-confirm-cancel');
    const ok = modal.querySelector('.js-crm-confirm-ok');
    const close = () => modal.classList.add('d-none');
    cancel.onclick = close;
    modal.onclick = e => { if (e.target === modal) close(); };
    ok.onclick = () => {
      form.dataset.confirmed = '1';
      if (submitter?.name && submitter?.value && submitter.name !== 'delete_all' && !submitter.classList.contains('js-bulk-submit')) {
        form.querySelectorAll(`input[type="checkbox"][name="${CSS.escape(submitter.name)}"]`).forEach(check => {
          if (check.value !== submitter.value) check.disabled = true;
        });
      }
      if (submitter) {
        submitter.classList.add('disabled');
        submitter.setAttribute('aria-disabled', 'true');
        submitter.style.pointerEvents = 'none';
        const keepCompactMaterialDelete = (
          document.documentElement.classList.contains('desktop-like-pointer')
          && submitter.classList.contains('material-writeoff-delete-btn')
        );
        if (keepCompactMaterialDelete) {
          const currentWidth = Math.ceil(submitter.getBoundingClientRect().width);
          if (currentWidth > 0) {
            submitter.style.width = `${currentWidth}px`;
            submitter.style.minWidth = `${currentWidth}px`;
          }
          submitter.classList.add('is-submitting');
        } else {
          submitter.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Удаление...';
        }
      }
      close();
      if (submitter) {
        form.requestSubmit(submitter);
      } else {
        form.requestSubmit();
      }
    };
  });
});

document.addEventListener('DOMContentLoaded', () => {
  const activateGlassType = (row, value) => {
    const hidden = row.querySelector('.js-glass-type-input');
    if (hidden) hidden.value = value || 'Стеклопакет';
    row.querySelectorAll('.js-glass-type-choice').forEach(btn => {
      btn.classList.toggle('is-active', btn.dataset.value === (value || 'Стеклопакет'));
    });
  };

  document.querySelectorAll('.js-glass-multi-form').forEach(form => {
    const container = form.querySelector('.js-glass-measure-items');
    const addButton = form.querySelector('.js-glass-add-item');
    if (!container || !addButton) return;

    const syncRemoveButtons = () => {
      const rows = container.querySelectorAll('.glass-measure-item-row');
      rows.forEach(row => {
        const removeButton = row.querySelector('.js-glass-remove-item');
        if (removeButton) removeButton.disabled = rows.length <= 1;
      });
    };

    container.addEventListener('click', event => {
      const typeButton = event.target.closest('.js-glass-type-choice');
      if (typeButton) {
        activateGlassType(typeButton.closest('.glass-measure-item-row'), typeButton.dataset.value);
        return;
      }
      const removeButton = event.target.closest('.js-glass-remove-item');
      if (!removeButton) return;
      const rows = container.querySelectorAll('.glass-measure-item-row');
      if (rows.length <= 1) return;
      removeButton.closest('.glass-measure-item-row')?.remove();
      syncRemoveButtons();
    });

    addButton.addEventListener('click', () => {
      const firstRow = container.querySelector('.glass-measure-item-row');
      if (!firstRow) return;
      const clone = firstRow.cloneNode(true);
      clone.querySelectorAll('input').forEach(input => {
        if (input.name.includes('quantity')) {
          input.value = '1';
        } else if (input.classList.contains('js-glass-type-input')) {
          input.value = 'Стеклопакет';
        } else {
          input.value = '';
        }
        input.classList.remove('is-invalid');
      });
      clone.querySelectorAll('select').forEach(select => {
        select.value = 'Стеклопакет';
        select.classList.remove('is-invalid');
        select.dataset.customSelectReady = '';
        select.removeAttribute('aria-hidden');
        select.tabIndex = 0;
      });
      clone.querySelectorAll('.developer-select-button').forEach(button => button.remove());
      clone.querySelectorAll('.developer-select-menu').forEach(menu => menu.remove());
      activateGlassType(clone, 'Стеклопакет');
      container.appendChild(clone);
      syncRemoveButtons();
    });

    container.querySelectorAll('.glass-measure-item-row').forEach(row => {
      const hidden = row.querySelector('.js-glass-type-input');
      activateGlassType(row, hidden?.value || 'Стеклопакет');
    });
    syncRemoveButtons();
  });

  const buildGlassNeedMeasureMarkup = (taskId, csrfToken) => `
    <form method="post" action="/glass/${taskId}/need-measure" class="js-glass-need-measure-form" data-task-id="${escapeHtml(taskId)}">
      <input type="hidden" name="csrf_token" value="${escapeHtml(csrfToken || getCsrfToken())}">
      <input type="hidden" name="return_tab" value="all">
      <button class="btn btn-sm btn-success glass-measure-icon-btn" type="submit" title="Сделать замер" aria-label="Сделать замер"><i class="bi bi-rulers"></i></button>
    </form>
  `;

  const buildGlassMeasureNeededMarkup = (measurementId, taskId, csrfToken) => {
    return `
      <div class="glass-all-row-actions">
        <span class="glass-status-badge glass-status-ordered">В заказе</span>
        <form method="post" action="/glass/${measurementId}/return-to-all" class="js-glass-return-form" data-task-id="${escapeHtml(taskId)}">
          <input type="hidden" name="csrf_token" value="${escapeHtml(csrfToken || getCsrfToken())}">
          <input type="hidden" name="return_tab" value="all">
          <button class="btn btn-sm btn-outline-secondary glass-measure-reset-btn" type="submit" title="Вернуть" aria-label="Вернуть"><i class="bi bi-arrow-counterclockwise"></i></button>
        </form>
      </div>
    `;
  };

  const bindGlassAllRowActions = actions => {
    if (!actions || actions.dataset.glassAllRowActionsBound === '1') return;
    actions.dataset.glassAllRowActionsBound = '1';
    actions.addEventListener('click', event => {
      event.stopPropagation();
    });
  };

  const bindGlassActionCell = cell => {
    if (!cell) return;
    bindGlassAllRowActions(cell.querySelector('.glass-all-row-actions'));
    bindGlassNeedMeasureForm(cell.querySelector('.js-glass-need-measure-form'));
    bindGlassReturnForm(cell.querySelector('.js-glass-return-form'));
  };

  const refreshGlassActionCell = async (taskId, cell) => {
    if (!taskId || !cell) return false;
    const response = await fetch(window.location.href, {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
      },
    });
    if (!response.ok) return false;
    const html = await response.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const nextRow = doc.querySelector(`.inline-text[data-task-id="${String(taskId)}"]`)?.closest('tr');
    const nextCell = nextRow?.querySelector('td.text-end');
    if (!nextCell) return false;
    cell.innerHTML = nextCell.innerHTML;
    bindGlassActionCell(cell);
    return true;
  };

  const syncGlassOrderListState = list => {
    if (!list) return;
    const cards = Array.from(list.querySelectorAll('.glass-order-card'));
    const emptyState = list.querySelector('.js-glass-order-empty-state');
    if (cards.length > 0) {
      emptyState?.remove();
      return;
    }
    if (emptyState) return;
    const nextEmptyState = document.createElement('div');
    nextEmptyState.className = 'glass-empty-state text-center text-muted py-5 js-glass-order-empty-state';
    nextEmptyState.textContent = 'Нет позиций для заказа. Нажмите иконку замера во вкладке «Все».';
    list.appendChild(nextEmptyState);
  };

  const syncGlassOrderedTableState = tbody => {
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll('.glass-order-row'));
    const emptyRow = tbody.querySelector('.js-glass-ordered-empty-row');
    if (rows.length > 0) {
      emptyRow?.remove();
      return;
    }
    if (emptyRow) return;
    const nextEmptyRow = document.createElement('tr');
    nextEmptyRow.className = 'js-glass-ordered-empty-row';
    nextEmptyRow.innerHTML = '<td colspan="8" class="text-center text-muted py-5">Нет позиций для текущего фильтра</td>';
    tbody.appendChild(nextEmptyRow);
  };

  const bindGlassNeedMeasureForm = form => {
    if (!form || form.dataset.glassNeedMeasureBound === '1') return;
    form.dataset.glassNeedMeasureBound = '1';
    form.addEventListener('click', event => {
      event.stopPropagation();
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.submitter || form.querySelector('button[type="submit"]');
      const previousHtml = button?.innerHTML || '';
      const csrfToken = form.querySelector('input[name="csrf_token"]')?.value || getCsrfToken();
      if (button) button.disabled = true;
      if (button) {
        button.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>';
        button.setAttribute('aria-busy', 'true');
      }
      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) throw new Error(data.message || 'Не удалось обновить статус');
        const cell = form.closest('td');
        const nextTaskId = data.task_id || form.dataset.taskId;
        let synced = false;
        if (cell && nextTaskId) {
          synced = await refreshGlassActionCell(nextTaskId, cell).catch(() => false);
        }
        if (!synced && cell && data.measurement_id && nextTaskId) {
          cell.innerHTML = buildGlassMeasureNeededMarkup(data.measurement_id, nextTaskId, csrfToken);
          bindGlassActionCell(cell);
          synced = true;
        }
        if (!synced) {
          window.setTimeout(() => window.location.reload(), 120);
        }
        showCrmNotice(data.message || 'Готово', 'success');
      } catch (error) {
        showCrmNotice(error.message || 'Не удалось обновить статус', 'danger');
        if (button) button.disabled = false;
      } finally {
        if (button) {
          button.innerHTML = previousHtml;
          button.removeAttribute('aria-busy');
        }
      }
    });
  };
  document.querySelectorAll('.js-glass-need-measure-form').forEach(bindGlassNeedMeasureForm);
  document.querySelectorAll('.glass-all-row-actions').forEach(bindGlassAllRowActions);

  const bindGlassReturnForm = form => {
    if (!form || form.dataset.glassReturnBound === '1') return;
    form.dataset.glassReturnBound = '1';
    form.addEventListener('click', event => {
      event.stopPropagation();
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.submitter || form.querySelector('button[type="submit"]');
      const previousHtml = button?.innerHTML || '';
      const cell = form.closest('td');
      const row = form.closest('tr');
      const taskId = form.dataset.taskId || row?.querySelector('.inline-text')?.dataset?.taskId;
      const csrfToken = form.querySelector('input[name="csrf_token"]')?.value || getCsrfToken();
      if (button) button.disabled = true;
      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) throw new Error(data.message || 'Не удалось обновить статус');
        const nextTaskId = taskId || data.task_id;
        let synced = false;
        if (cell && nextTaskId) {
          synced = await refreshGlassActionCell(nextTaskId, cell).catch(() => false);
        }
        if (!synced && cell && nextTaskId) {
          cell.innerHTML = buildGlassNeedMeasureMarkup(nextTaskId, csrfToken);
          bindGlassActionCell(cell);
          synced = true;
        }
        if (!synced) {
          window.setTimeout(() => window.location.reload(), 120);
        }
        showCrmNotice(data.message || 'Готово', 'success');
      } catch (error) {
        showCrmNotice(error.message || 'Не удалось обновить статус', 'danger');
        if (button) button.disabled = false;
      } finally {
        if (button) button.innerHTML = previousHtml;
      }
    });
  };
  document.querySelectorAll('.js-glass-return-form').forEach(bindGlassReturnForm);

  const bindGlassSaveForm = form => {
    if (!form || form.dataset.glassSaveBound === '1') return;
    form.dataset.glassSaveBound = '1';
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.submitter || form.querySelector('button[type="submit"]');
      const previousHtml = button?.innerHTML || '';
      if (button) button.disabled = true;
      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) throw new Error(data.message || 'Не удалось сохранить размеры');
        const savedRow = form.closest('.glass-order-card, .glass-order-row');
        savedRow?.classList.add('glass-row-saved');
        if (!form.classList.contains('js-glass-ordered-edit-form')) {
          const orderList = savedRow?.closest('.glass-order-list');
          savedRow?.remove();
          syncGlassOrderListState(orderList);
        } else {
          const view = savedRow?.querySelector('.js-glass-ordered-size-view');
          if (view && Array.isArray(data.items)) {
            view.innerHTML = data.items.map(item => `
              <div class="glass-ordered-size-line glass-ordered-size-line-readable">
                <span><b>Тип:</b> ${escapeHtml(item.item_type || '—')}</span>
                <span><b>Размер:</b> ${escapeHtml(item.size_input || item.size_label || '—')}</span>
                <span><b>Кол-во:</b> ${escapeHtml(item.quantity || 1)}</span>
                <span class="glass-ordered-size-comment"><b>Комментарий:</b> ${escapeHtml(item.item_comment || '—')}</span>
              </div>
            `).join('');
          }
          view?.classList.remove('d-none');
          form.classList.add('d-none');
          form.hidden = true;
          savedRow?.classList.remove('glass-order-editing');
        }
        showCrmNotice(data.message || 'Размеры перенесены в заказ', 'success');
      } catch (error) {
        showCrmNotice(error.message || 'Не удалось сохранить размеры', 'danger');
      } finally {
        if (button) {
          button.disabled = false;
          button.innerHTML = previousHtml;
        }
      }
    });
  };
  const initGlassOrderedEditScope = scope => {
    const root = scope && typeof scope.querySelectorAll === 'function' ? scope : document;

    root.querySelectorAll('.js-glass-save-form').forEach(bindGlassSaveForm);

    root.querySelectorAll('.js-glass-ordered-edit-toggle').forEach(button => {
      if (button.dataset.glassOrderedEditBound === '1') return;
      button.dataset.glassOrderedEditBound = '1';
      button.addEventListener('click', () => {
        const row = button.closest('.glass-order-row');
        const form = row?.querySelector('.js-glass-ordered-edit-form');
        const view = row?.querySelector('.js-glass-ordered-size-view');
        if (!form) return;
        row?.classList.add('glass-order-editing');
        view?.classList.add('d-none');
        form.classList.remove('d-none');
        form.hidden = false;
        const firstInput = form.querySelector('input, select, textarea');
        firstInput?.focus();
      });
    });

    root.querySelectorAll('.js-glass-ordered-edit-cancel').forEach(button => {
      if (button.dataset.glassOrderedEditCancelBound === '1') return;
      button.dataset.glassOrderedEditCancelBound = '1';
      button.addEventListener('click', () => {
        const form = button.closest('.js-glass-ordered-edit-form');
        const row = form?.closest('.glass-order-row');
        const view = row?.querySelector('.js-glass-ordered-size-view');
        form?.classList.add('d-none');
        if (form) form.hidden = true;
        row?.classList.remove('glass-order-editing');
        view?.classList.remove('d-none');
      });
    });
  };
  initGlassOrderedEditScope(document);

  const bindGlassStatusForm = form => {
    if (!form || form.dataset.glassStatusBound === '1') return;
    form.dataset.glassStatusBound = '1';
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.submitter || form.querySelector('button[type="submit"]');
      if (!button) return;
      const previousHtml = button.innerHTML;
      form.querySelectorAll('button').forEach(item => { item.disabled = true; });
      try {
        const formData = new FormData(form);
        if (button.name) {
          formData.set(button.name, button.value ?? '');
        }
        const response = await fetch(form.action, {
          method: 'POST',
          body: formData,
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) throw new Error(data.message || 'Не удалось обновить статус');
        const tableRow = form.closest('.glass-order-row');
        const orderedFilterValue = document.querySelector('select[name="ordered_status"]')?.value || '';
        if (orderedFilterValue && orderedFilterValue !== data.status && tableRow) {
          const checkbox = tableRow.querySelector('.js-bulk-check');
          if (checkbox && checkbox.checked) {
            checkbox.checked = false;
            checkbox.dispatchEvent(new Event('change', { bubbles: true }));
          }
          const bulkScope = tableRow.closest('.js-bulk-selectable');
          const tbody = tableRow.parentElement;
          tableRow.remove();
          if (bulkScope) syncBulkScope(bulkScope);
          syncGlassOrderedTableState(tbody);
          showCrmNotice(data.message || 'Статус обновлён', 'success');
          return;
        }
        form.querySelectorAll('.glass-status-choice').forEach(item => {
          const isActive = item.value === data.status;
          item.classList.toggle('is-active', isActive);
          item.classList.toggle('is-ordered', isActive && item.value === 'ordered');
          item.classList.toggle('is-replaced', isActive && item.value === 'replaced');
        });
        const dateCell = form.closest('tr')?.children?.[4];
        const statusCell = form.closest('td');
        if (dateCell && data.ordered_at) {
          dateCell.textContent = data.ordered_at;
        }
        if (statusCell) {
          const replacedNote = statusCell.querySelector('.small.text-success');
          if (data.status === 'replaced' && data.replaced_at) {
            if (replacedNote) {
              replacedNote.textContent = `Поменяно: ${data.replaced_at}`;
            } else {
              const note = document.createElement('div');
              note.className = 'small text-success mt-1';
              note.textContent = `Поменяно: ${data.replaced_at}`;
              statusCell.appendChild(note);
            }
          } else if (replacedNote) {
            replacedNote.remove();
          }
        }
        showCrmNotice(data.message || 'Статус обновлён', 'success');
      } catch (error) {
        showCrmNotice(error.message || 'Не удалось обновить статус', 'danger');
      } finally {
        form.querySelectorAll('button').forEach(item => { item.disabled = false; });
        button.innerHTML = previousHtml;
      }
    });
  };
  const initGlassPageScope = scope => {
    const root = scope && typeof scope.querySelectorAll === 'function' ? scope : document;
    root.querySelectorAll('.js-glass-need-measure-form').forEach(bindGlassNeedMeasureForm);
    root.querySelectorAll('.glass-all-row-actions').forEach(bindGlassAllRowActions);
    root.querySelectorAll('.js-glass-return-form').forEach(bindGlassReturnForm);
    root.querySelectorAll('.js-glass-status-form').forEach(bindGlassStatusForm);
    initGlassOrderedEditScope(root);
  };
  initGlassPageScope(document);

  document.addEventListener('crm:ajax-pagination-updated', event => {
    initGlassPageScope(event.detail?.content || document);
  });

  const glassManualModalElement = document.getElementById('glassManualTaskModal');
  const glassManualForm = document.querySelector('.js-glass-manual-form');
  const glassManualModal = glassManualModalElement && window.bootstrap ? new bootstrap.Modal(glassManualModalElement) : null;
  document.addEventListener('click', event => {
    if (event.target.closest('.js-glass-manual-open')) glassManualModal?.show();
  });
  glassManualForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const button = event.submitter || glassManualForm.querySelector('button[type="submit"]');
    const previousHtml = button?.innerHTML || '';
    if (button) button.disabled = true;
    try {
      const response = await fetch(glassManualForm.action, {
        method: 'POST',
        body: new FormData(glassManualForm),
        credentials: 'same-origin',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'application/json',
        },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) throw new Error(data.message || 'Не удалось добавить замечание');
      const tbody = document.querySelector('.glass-page table tbody');
      if (tbody && document.querySelector('input[name="tab"][value="all"]')) {
        const row = document.createElement('tr');
        row.className = 'task-row-link';
        row.dataset.href = data.task_url || '';
        row.innerHTML = `
          <td><span class="js-highlight-text">${escapeHtml(data.apartment_label || '—')}</span></td>
          <td class="task-text"><span class="inline-text js-highlight-text" data-task-id="${escapeHtml(data.task_id || '')}">${escapeHtml(data.description || '')}</span></td>
          <td><span class="badge bg-${escapeHtml(data.status_class || 'secondary')}">${escapeHtml(data.status_label || '')}</span></td>
          <td class="text-end">
            <form method="post" action="/glass/${data.task_id}/need-measure" class="js-glass-need-measure-form" data-task-id="${escapeHtml(data.task_id || '')}">
              <input type="hidden" name="csrf_token" value="${escapeHtml(getCsrfToken())}">
              <input type="hidden" name="return_tab" value="all">
              <button class="btn btn-sm btn-success glass-measure-icon-btn" type="submit" title="Сделать замер" aria-label="Сделать замер"><i class="bi bi-rulers"></i></button>
            </form>
          </td>
        `;
        tbody.prepend(row);
        bindTaskRowLink(row);
        bindGlassNeedMeasureForm(row.querySelector('.js-glass-need-measure-form'));
      }
      glassManualForm.reset();
      glassManualModal?.hide();
      showCrmNotice(data.message || 'Замечание добавлено', 'success');
    } catch (error) {
      showCrmNotice(error.message || 'Не удалось добавить замечание', 'danger');
    } finally {
      if (button) {
        button.disabled = false;
        button.innerHTML = previousHtml;
      }
    }
  });
});

// Site-wide custom validation: no ugly browser bubbles, only CRM-style messages.
document.addEventListener('DOMContentLoaded', () => {
  const ensureValidationToast = () => {
    let toast = document.querySelector('.js-crm-validation-toast');
    if (toast) return toast;
    toast = document.createElement('div');
    toast.className = 'crm-validation-toast js-crm-validation-toast d-none';
    toast.innerHTML = `
      <div class="crm-validation-toast-icon"><i class="bi bi-exclamation-circle"></i></div>
      <div>
        <div class="crm-validation-toast-title">Заполните обязательные поля</div>
        <div class="crm-validation-toast-text">Проверьте выделенные поля и попробуйте ещё раз.</div>
      </div>
      <button class="crm-validation-toast-close" type="button" aria-label="Закрыть"><i class="bi bi-x-lg"></i></button>`;
    document.body.appendChild(toast);
    toast.querySelector('.crm-validation-toast-close')?.addEventListener('click', () => toast.classList.add('d-none'));
    return toast;
  };

  const showValidationToast = (message) => {
    const toast = ensureValidationToast();
    const text = toast.querySelector('.crm-validation-toast-text');
    if (text) text.textContent = message || 'Проверьте выделенные поля и попробуйте ещё раз.';
    toast.classList.remove('d-none');
    window.clearTimeout(toast._hideTimer);
    toast._hideTimer = window.setTimeout(() => toast.classList.add('d-none'), 4200);
  };

  document.querySelectorAll('form').forEach(form => {
    if (form.dataset.nativeValidation === '1') return;
    form.noValidate = true;
    form.addEventListener('input', event => {
      const field = event.target.closest('input, select, textarea');
      if (field && field.checkValidity()) field.classList.remove('is-invalid');
    });
    form.addEventListener('change', event => {
      const field = event.target.closest('input, select, textarea');
      if (field && field.checkValidity()) field.classList.remove('is-invalid');
    });
  });

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.nativeValidation === '1') return;
    if (form.checkValidity()) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    const invalidFields = Array.from(form.querySelectorAll('input, select, textarea'))
      .filter(field => !field.disabled && field.type !== 'hidden' && !field.checkValidity());
    invalidFields.forEach(field => field.classList.add('is-invalid'));
    const firstVisible = invalidFields.find(field => field.offsetParent !== null) || invalidFields[0];
    if (firstVisible) {
      firstVisible.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => firstVisible.focus({ preventScroll: true }), 250);
    }
    showValidationToast('Заполните выделенные поля. Обязательные поля подсвечены красным.');
  }, true);
});

document.addEventListener('DOMContentLoaded', () => {
  const updateDocumentFieldVisibility = (blocks, visible) => {
    blocks.forEach(block => {
      block.style.display = visible ? '' : 'none';
      block.querySelectorAll('.js-document-field-control').forEach(control => {
        control.disabled = !visible;
        if (control.dataset.required === '1') {
          control.required = visible;
        }
      });
    });
  };

  const applyOwnerGenderTemplate = (genderFieldId, dataFieldId) => {
    const gender = document.getElementById(genderFieldId);
    const data = document.getElementById(dataFieldId);
    if (!gender || !data) return;
    const template = gender.value === 'male' ? data.dataset.ownerTemplateMale : data.dataset.ownerTemplateFemale;
    if (!template) return;
    const previousTemplate = data.dataset.lastOwnerTemplate || '';
    const current = data.value.trim();
    if (!current || current === previousTemplate) {
      data.value = template;
      data.dispatchEvent(new Event('input', { bubbles: true }));
    }
    data.dataset.lastOwnerTemplate = template;
  };

  const updateDocumentOwnerFields = () => {
    const selected = document.querySelector('.js-owner-count:checked')?.value || '1';
    updateDocumentFieldVisibility(document.querySelectorAll('.js-owner-two-field'), selected === '2');
    updateDocumentFieldVisibility(document.querySelectorAll('.js-owner-one-field'), selected !== '2');
    const ownerOneLabel = document.querySelector('label[for="field-owner_one_data"]');
    if (ownerOneLabel) {
      const marker = ownerOneLabel.querySelector('.required-dot')?.outerHTML || '';
      ownerOneLabel.innerHTML = `${selected === '2' ? 'Данные 1 собственника' : 'Данные собственника'}${marker}`;
    }
    applyOwnerGenderTemplate('field-owner_one_gender', 'field-owner_one_data');
    applyOwnerGenderTemplate('field-owner_two_gender', 'field-owner_two_data');
  };

  document.querySelectorAll('.js-owner-count').forEach(input => {
    input.addEventListener('change', updateDocumentOwnerFields);
  });
  ['field-owner_one_gender', 'field-owner_two_gender'].forEach(id => {
    const field = document.getElementById(id);
    if (field) field.addEventListener('change', updateDocumentOwnerFields);
  });
  updateDocumentOwnerFields();

  document.querySelectorAll('.js-document-choice-btn').forEach(button => {
    button.addEventListener('click', () => {
      const group = button.closest('.document-choice-group');
      const target = document.getElementById(group?.dataset.choiceTarget || '');
      if (!group || !target) return;
      target.value = button.dataset.value || '';
      group.querySelectorAll('.js-document-choice-btn').forEach(item => item.classList.toggle('is-active', item === button));
      target.dispatchEvent(new Event('change', { bubbles: true }));
      target.dispatchEvent(new Event('input', { bubbles: true }));

      if (button.classList.contains('js-document-transfer-btn')) {
        const materials = document.getElementById('field-materials_block');
        const acceptance = document.getElementById('field-acceptance_text');
        if (materials && button.dataset.materialsTemplate) {
          materials.value = button.dataset.materialsTemplate;
          materials.dispatchEvent(new Event('input', { bubbles: true }));
        }
        if (acceptance && button.dataset.acceptance) {
          acceptance.value = button.dataset.acceptance;
          acceptance.dispatchEvent(new Event('input', { bubbles: true }));
        }
      }
    });
  });

  document.querySelectorAll('.js-document-quick-insert').forEach(button => {
    button.addEventListener('click', () => {
      const target = document.getElementById(button.dataset.target || '');
      if (!target) return;
      target.value = button.dataset.value || '';
      target.dispatchEvent(new Event('input', { bubbles: true }));
      target.focus();
    });
  });

  document.querySelectorAll('.document-upload-drop input[type="file"]').forEach(input => {
    input.addEventListener('change', () => {
      const label = input.closest('.document-upload-drop')?.querySelector('small');
      if (label && input.files && input.files[0]) label.textContent = input.files[0].name;
    });
  });
});

// Mobile object search: keeps the objects page lightweight without changing server-side routes.
document.addEventListener('DOMContentLoaded', () => {
  const objectSearch = document.querySelector('[data-object-search]');
  if (!objectSearch) return;
  const searchField = objectSearch.closest('.mobile-search-field');
  const cards = Array.from(document.querySelectorAll('.object-card'));
  const focusSearch = () => {
    try {
      objectSearch.focus({ preventScroll: true });
    } catch (error) {
      objectSearch.focus();
    }
  };

  if (searchField) {
    searchField.addEventListener('pointerdown', event => {
      event.stopPropagation();
      if (event.target === objectSearch) return;
      event.preventDefault();
      focusSearch();
    });
    searchField.addEventListener('click', event => {
      event.stopPropagation();
      if (event.target === objectSearch) return;
      focusSearch();
    });
  }

  objectSearch.addEventListener('pointerdown', event => {
    event.stopPropagation();
  });
  objectSearch.addEventListener('click', event => {
    event.stopPropagation();
  });

  objectSearch.addEventListener('input', () => {
    const query = objectSearch.value.trim().toLowerCase();
    cards.forEach(card => {
      const haystack = card.textContent.toLowerCase();
      card.hidden = Boolean(query) && !haystack.includes(query);
    });
  });
});

document.addEventListener('DOMContentLoaded', () => {
  const resultPage = document.querySelector('.js-document-result-page');
  const editor = document.querySelector('.js-document-editor');
  const editBack = document.querySelector('.js-document-edit-back');
  if (!resultPage || !editor || !editBack) return;

  const showEditor = () => {
    resultPage.classList.add('is-hidden-for-edit');
    editor.classList.remove('document-editor-hidden');
    editor.classList.add('is-visible-after-result');
    const heading = editor.querySelector('.document-flow-section-head .section-title') || editor;
    requestAnimationFrame(() => heading.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };

  editBack.addEventListener('click', showEditor);
});

document.addEventListener('DOMContentLoaded', () => {
  const list = document.querySelector('[data-worker-task-list]');
  if (!list) return;

  const updateCounters = (wasDone, isDone) => {
    if (wasDone === isDone) return;
    const doneEl = document.querySelector('[data-worker-done-count]');
    const leftEl = document.querySelector('[data-worker-left-count]');
    if (!doneEl || !leftEl) return;
    const done = parseInt(doneEl.textContent || '0', 10) || 0;
    const left = parseInt(leftEl.textContent || '0', 10) || 0;
    doneEl.textContent = String(Math.max(0, done + (isDone ? 1 : -1)));
    leftEl.textContent = String(Math.max(0, left + (isDone ? -1 : 1)));
  };

  list.addEventListener('submit', async event => {
    const form = event.target.closest('[data-worker-status-form]');
    if (!form) return;
    event.preventDefault();

    const card = form.closest('[data-worker-task-card]');
    const button = form.querySelector('button[type="submit"]');
    const pill = card?.querySelector('[data-worker-status-pill]');
    const wasDone = card?.classList.contains('done') || false;
    const previousHtml = button?.innerHTML || '';
    const previousDisabled = button?.disabled || false;
    if (button) {
      button.disabled = true;
      button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Сохраняю';
    }

    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
        credentials: 'same-origin'
      });
      if (!response.ok) throw new Error('request failed');
      const data = await response.json();
      if (!data || !data.ok) throw new Error('bad payload');

      if (card) {
        card.classList.toggle('done', Boolean(data.is_done));
        if (window.moveDoneItemToBottom) window.moveDoneItemToBottom(card);
      }
      if (pill) {
        pill.className = `worker-status-pill badge bg-${data.status_class || 'secondary'}`;
        pill.textContent = data.status_label || (data.is_done ? 'Выполнено' : 'Не выполнено');
      }

      const currentAction = form.action;
      const nextUrl = form.dataset.nextUrl;
      if (nextUrl) {
        form.action = nextUrl;
        form.dataset.nextUrl = currentAction;
      }
      if (button) {
        button.disabled = false;
        if (data.is_done) {
          button.className = 'btn worker-status-btn worker-status-btn-return';
          button.innerHTML = '<i class="bi bi-arrow-counterclockwise"></i><span>Не выполнено</span>';
        } else {
          button.className = 'btn worker-status-btn worker-status-btn-done';
          button.innerHTML = '<i class="bi bi-check2"></i><span>Выполнено</span>';
        }
      }
      updateCounters(wasDone, Boolean(data.is_done));
    } catch (error) {
      if (button) {
        button.disabled = previousDisabled;
        button.innerHTML = previousHtml;
      }
      form.submit();
    }
  });
});

document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('[data-avr-form]');
  if (!form) return;

  const source = form.querySelector('[data-avr-apartments]');
  const select = form.querySelector('[data-avr-apartment]');
  const modalElement = form.querySelector('[data-avr-modal]');
  const openModalButton = form.querySelector('[data-avr-open-modal]');
  const desktopAvrModal = document.documentElement.classList.contains('desktop-like-pointer');
  const associateModalControls = () => {
    if (!desktopAvrModal || !modalElement) return;
    if (!form.id) form.id = 'avrForm';
    modalElement.querySelectorAll('input, select, textarea, button[type="submit"]').forEach(control => {
      control.setAttribute('form', form.id);
    });
  };

  // A modal left inside the animated page surface is trapped in that surface's
  // stacking context, while Bootstrap places its backdrop directly under body.
  // Put both layers at the same root so the dialog always receives pointer events.
  if (modalElement && desktopAvrModal) {
    associateModalControls();
    if (modalElement.parentElement !== document.body) {
      document.body.append(modalElement);
    }
  }
  const modal = modalElement && window.bootstrap ? bootstrap.Modal.getOrCreateInstance(modalElement) : null;
  if (desktopAvrModal) {
    modalElement?.querySelectorAll('[data-avr-close]').forEach(button => {
      button.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        modal?.hide();
      });
    });

    // Closing the dialog must never be treated as an implicit form submit.
    // Only the explicit download button is allowed to send the AVR form.
    form.addEventListener('submit', event => {
      if (event.submitter?.matches('[data-avr-download]')) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    }, true);
  }
  modalElement?.addEventListener('show.bs.modal', () => {
    if (document.documentElement.classList.contains('desktop-like-pointer')) {
      document.documentElement.classList.add('avr-modal-open');
    }
  });
  modalElement?.addEventListener('hidden.bs.modal', () => {
    document.documentElement.classList.remove('avr-modal-open');
  });
  let apartments = [];
  try {
    apartments = JSON.parse(source?.textContent || '[]');
  } catch (error) {
    apartments = [];
  }

  const fields = {
    number: modalElement?.querySelector('[data-avr-number]'),
    floor: modalElement?.querySelector('[data-avr-floor]'),
    floorField: modalElement?.querySelector('[data-avr-floor-field]'),
    owner: modalElement?.querySelector('[data-avr-owner]'),
    address: modalElement?.querySelector('[data-avr-address]'),
    inspectionDate: form.querySelector('[data-avr-inspection-date]'),
    premiseType: form.querySelector('[data-avr-premise-type]'),
    phrase: modalElement?.querySelector('[data-avr-phrase]')
  };

  const formatRuDate = value => {
    if (!value) return '__.__.____';
    const parts = String(value).split('-');
    if (parts.length !== 3) return value;
    return `${parts[2]}.${parts[1]}.${parts[0]}`;
  };

  const phraseForDate = value => `Все замечания с акта осмотра от ${formatRuDate(value)} устранены.`;

  const setOwnerOptions = selected => {
    if (!fields.owner) return;
    const options = Array.isArray(selected.owner_options) && selected.owner_options.length
      ? selected.owner_options
      : [selected.owner || ''].filter(Boolean);
    fields.owner.innerHTML = '';
    options.forEach((owner, index) => {
      const label = document.createElement('label');
      label.className = 'form-check';
      const input = document.createElement('input');
      input.className = 'form-check-input';
      input.type = 'checkbox';
      input.name = 'owner_names';
      input.value = owner;
      input.checked = index === 0;
      const text = document.createElement('span');
      text.className = 'form-check-label';
      text.textContent = owner;
      label.appendChild(input);
      label.appendChild(text);
      fields.owner.appendChild(label);
    });
    associateModalControls();
  };

  const applyApartment = () => {
    const selected = apartments.find(item => String(item.id) === String(select?.value));
    if (!selected) return null;
    const isCommercial = selected.premise_type === 'commercial';
    if (fields.number) fields.number.value = selected.number || '';
    if (fields.floor) fields.floor.value = selected.floor || '';
    if (fields.floor) fields.floor.required = !isCommercial;
    if (fields.floorField) fields.floorField.hidden = isCommercial;
    if (fields.premiseType) fields.premiseType.value = selected.premise_type || 'apartment';
    setOwnerOptions(selected);
    if (fields.address) fields.address.value = selected.address || '';
    if (fields.inspectionDate) fields.inspectionDate.value = selected.inspection_date || '';
    if (fields.phrase) {
      const nextPhrase = selected.phrase || phraseForDate(selected.inspection_date);
      fields.phrase.value = nextPhrase;
      fields.phrase.dataset.autoPhrase = nextPhrase;
    }
    return selected;
  };

  const openApartmentModal = () => {
    const selected = applyApartment();
    if (selected && modal) {
      associateModalControls();
      modal.show();
    }
  };

  select?.addEventListener('change', openApartmentModal);
  openModalButton?.addEventListener('click', openApartmentModal);
  fields.inspectionDate?.addEventListener('change', () => {
    if (!fields.phrase) return;
    const nextPhrase = phraseForDate(fields.inspectionDate.value);
    if (!fields.phrase.value.trim() || fields.phrase.value === fields.phrase.dataset.autoPhrase) {
      fields.phrase.value = nextPhrase;
    }
    fields.phrase.dataset.autoPhrase = nextPhrase;
  });
});

document.addEventListener('DOMContentLoaded', () => {
  const page = document.querySelector('.assignment-report-page');
  if (!page) return;

  const reportPad2 = value => String(value).padStart(2, '0');
  const reportToIsoDate = date => `${date.getFullYear()}-${reportPad2(date.getMonth() + 1)}-${reportPad2(date.getDate())}`;
  const reportParseIsoDate = value => {
    const parts = String(value || '').split('-').map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return new Date();
    return new Date(parts[0], parts[1] - 1, parts[2]);
  };
  const reportPrettyDate = value => {
    const date = reportParseIsoDate(value);
    return `${reportPad2(date.getDate())}.${reportPad2(date.getMonth() + 1)}.${date.getFullYear()}`;
  };

  const ensureReportDateModal = () => {
    let modal = document.querySelector('.js-assignment-report-date-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'assignment-date-modal-overlay js-assignment-report-date-modal d-none';
    modal.innerHTML = `
      <div class="assignment-date-modal assignment-report-date-modal" role="dialog" aria-modal="true" aria-labelledby="assignment-report-date-modal-title">
        <div class="assignment-date-modal-head">
          <div>
            <div class="assignment-date-modal-kicker">Дата отчета</div>
            <h2 id="assignment-report-date-modal-title">Выбор даты</h2>
          </div>
          <button class="assignment-date-modal-close js-assignment-report-date-cancel" type="button" aria-label="Закрыть"><i class="bi bi-x-lg"></i></button>
        </div>
        <div class="assignment-date-quick-row">
          <button type="button" class="js-assignment-report-date-quick" data-offset="0">Сегодня</button>
          <button type="button" class="js-assignment-report-date-quick" data-offset="-1">Вчера</button>
          <button type="button" class="js-assignment-report-date-quick" data-offset="-7">Неделю назад</button>
        </div>
        <div class="assignment-date-calendar">
          <div class="assignment-date-calendar-head">
            <button type="button" class="assignment-date-nav js-assignment-report-date-prev" aria-label="Предыдущий месяц"><i class="bi bi-chevron-left"></i></button>
            <div class="assignment-date-month js-assignment-report-date-month"></div>
            <button type="button" class="assignment-date-nav js-assignment-report-date-next" aria-label="Следующий месяц"><i class="bi bi-chevron-right"></i></button>
          </div>
          <div class="assignment-date-weekdays"><span>Пн</span><span>Вт</span><span>Ср</span><span>Чт</span><span>Пт</span><span>Сб</span><span>Вс</span></div>
          <div class="assignment-date-grid js-assignment-report-date-grid"></div>
        </div>
        <div class="assignment-date-selected">
          <span>Выбрано</span>
          <b class="js-assignment-report-date-selected-text"></b>
        </div>
        <div class="assignment-date-modal-actions">
          <button class="btn btn-outline-secondary js-assignment-report-date-cancel" type="button">Отмена</button>
          <button class="btn btn-primary js-assignment-report-date-save" type="button"><i class="bi bi-check2"></i><span>Выбрать дату</span></button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    return modal;
  };

  const openReportDateModal = picker => {
    const input = picker.querySelector('.js-assignment-report-date-input');
    const button = picker.querySelector('.js-assignment-report-date-open');
    const valueText = picker.querySelector('.js-assignment-report-date-value');
    if (!input || !button || !valueText) return;

    const modal = ensureReportDateModal();
    let selectedIso = input.value || button.dataset.currentDate || reportToIsoDate(new Date());
    let viewDate = reportParseIsoDate(selectedIso);
    viewDate.setDate(1);

    const monthEl = modal.querySelector('.js-assignment-report-date-month');
    const gridEl = modal.querySelector('.js-assignment-report-date-grid');
    const selectedEl = modal.querySelector('.js-assignment-report-date-selected-text');
    const saveBtn = modal.querySelector('.js-assignment-report-date-save');

    const render = () => {
      const monthLabel = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(viewDate);
      monthEl.textContent = monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1);
      selectedEl.textContent = reportPrettyDate(selectedIso);
      gridEl.innerHTML = '';

      const year = viewDate.getFullYear();
      const month = viewDate.getMonth();
      const first = new Date(year, month, 1);
      const firstWeekDay = (first.getDay() + 6) % 7;
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const todayIso = reportToIsoDate(new Date());

      for (let i = 0; i < firstWeekDay; i += 1) {
        const spacer = document.createElement('span');
        spacer.className = 'assignment-date-day-spacer';
        gridEl.appendChild(spacer);
      }
      for (let day = 1; day <= daysInMonth; day += 1) {
        const date = new Date(year, month, day);
        const iso = reportToIsoDate(date);
        const dayButton = document.createElement('button');
        dayButton.type = 'button';
        dayButton.className = 'assignment-date-day';
        dayButton.textContent = String(day);
        dayButton.classList.toggle('is-selected', iso === selectedIso);
        dayButton.classList.toggle('is-today', iso === todayIso);
        dayButton.addEventListener('click', () => {
          selectedIso = iso;
          render();
        });
        gridEl.appendChild(dayButton);
      }
    };

    const close = () => {
      modal.classList.add('d-none');
      document.removeEventListener('keydown', onKeydown);
    };
    const onKeydown = event => {
      if (event.key === 'Escape') close();
    };

    modal.querySelectorAll('.js-assignment-report-date-cancel').forEach(cancel => { cancel.onclick = close; });
    modal.querySelector('.js-assignment-report-date-prev').onclick = () => {
      viewDate.setMonth(viewDate.getMonth() - 1);
      render();
    };
    modal.querySelector('.js-assignment-report-date-next').onclick = () => {
      viewDate.setMonth(viewDate.getMonth() + 1);
      render();
    };
    modal.querySelectorAll('.js-assignment-report-date-quick').forEach(quick => {
      quick.onclick = () => {
        const next = new Date();
        next.setDate(next.getDate() + Number(quick.dataset.offset || 0));
        selectedIso = reportToIsoDate(next);
        viewDate = reportParseIsoDate(selectedIso);
        viewDate.setDate(1);
        render();
      };
    });
    modal.onclick = event => { if (event.target === modal) close(); };
    saveBtn.onclick = () => {
      input.value = selectedIso;
      button.dataset.currentDate = selectedIso;
      valueText.textContent = reportPrettyDate(selectedIso);
      close();
    };

    render();
    document.addEventListener('keydown', onKeydown);
    modal.classList.remove('d-none');
  };

  page.querySelectorAll('.js-assignment-report-date-picker').forEach(picker => {
    picker.querySelector('.js-assignment-report-date-open')?.addEventListener('click', event => {
      event.preventDefault();
      openReportDateModal(picker);
    });
  });

  const numberFromText = element => {
    const match = String(element?.textContent || '').match(/\d+/);
    return match ? parseInt(match[0], 10) || 0 : 0;
  };
  const setNumber = (element, value) => {
    if (element) element.textContent = String(Math.max(0, value));
  };
  const setBadgeNumber = (element, label, value) => {
    if (element) element.textContent = `${label} ${Math.max(0, value)}`;
  };
  const showInlineNotice = message => {
    let stack = document.querySelector('.crm-toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'flash-stack crm-toast-stack';
      stack.setAttribute('aria-live', 'polite');
      stack.setAttribute('aria-atomic', 'true');
      document.body.appendChild(stack);
    }
    const toast = document.createElement('div');
    toast.className = 'alert alert-danger alert-dismissible fade show crm-toast crm-toast-danger';
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
      <div class="crm-toast-icon"><i class="bi bi-x-circle"></i></div>
      <div class="crm-toast-body">
        <div class="crm-toast-title">Ошибка</div>
        <div class="crm-toast-text">${message}</div>
      </div>
      <button type="button" class="crm-toast-close" aria-label="Закрыть"><i class="bi bi-x-lg"></i></button>
    `;
    stack.appendChild(toast);
    const close = () => toast.remove();
    toast.querySelector('.crm-toast-close')?.addEventListener('click', close);
    window.setTimeout(close, 4200);
  };
  const updateCounters = (card, wasDone, isDone) => {
    if (wasDone === isDone) return;
    const doneDelta = isDone ? 1 : -1;
    const leftDelta = isDone ? -1 : 1;
    setNumber(page.querySelector('[data-assignment-report-total-done]'), numberFromText(page.querySelector('[data-assignment-report-total-done]')) + doneDelta);
    setNumber(page.querySelector('[data-assignment-report-total-left]'), numberFromText(page.querySelector('[data-assignment-report-total-left]')) + leftDelta);
    setBadgeNumber(card?.querySelector('[data-assignment-report-group-done]'), 'выполнено', numberFromText(card?.querySelector('[data-assignment-report-group-done]')) + doneDelta);
    setBadgeNumber(card?.querySelector('[data-assignment-report-group-left]'), 'осталось', numberFromText(card?.querySelector('[data-assignment-report-group-left]')) + leftDelta);
  };

  page.addEventListener('submit', async event => {
    const form = event.target.closest('[data-assignment-report-status-form]');
    if (!form || !page.contains(form)) return;
    event.preventDefault();

    const row = form.closest('[data-assignment-report-row]');
    const card = form.closest('[data-assignment-report-card]');
    const button = form.querySelector('button[type="submit"]');
    const pill = row?.querySelector('[data-assignment-report-status-pill]');
    const wasDone = row?.classList.contains('is-done') || false;
    const previousHtml = button?.innerHTML || '';
    const previousClass = button?.className || '';
    const previousTitle = button?.getAttribute('title') || '';
    const previousAria = button?.getAttribute('aria-label') || '';
    const previousDisabled = button?.disabled || false;

    if (button) {
      button.disabled = true;
      button.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>';
    }

    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
        credentials: 'same-origin'
      });
      if (!response.ok) throw new Error('request failed');
      const data = await response.json();
      if (!data || data.ok === false) throw new Error('bad payload');

      const isDone = Boolean(data.is_done);
      row?.classList.toggle('is-done', isDone);
      if (pill) {
        pill.className = `badge bg-${data.status_class || (isDone ? 'success' : 'secondary')}`;
        pill.setAttribute('data-assignment-report-status-pill', '');
        pill.textContent = data.status_label || (isDone ? 'Выполнено' : 'Не выполнено');
      }
      const nextUrl = form.dataset.nextUrl;
      if (nextUrl) {
        const currentUrl = form.action;
        form.action = nextUrl;
        form.dataset.nextUrl = currentUrl;
      }
      if (button) {
        button.disabled = false;
        if (isDone) {
          button.className = 'btn btn-sm btn-outline-secondary assignment-report-return-btn';
          button.removeAttribute('title');
          button.removeAttribute('aria-label');
          button.innerHTML = '<i class="bi bi-arrow-counterclockwise me-1"></i>Вернуть';
        } else {
          button.className = 'btn btn-sm btn-success assignment-report-done-btn';
          button.setAttribute('title', 'Выполнено');
          button.setAttribute('aria-label', 'Выполнено');
          button.innerHTML = '<i class="bi bi-check2-circle"></i>';
        }
      }
      updateCounters(card, wasDone, isDone);
    } catch (error) {
      if (button) {
        button.disabled = previousDisabled;
        button.className = previousClass;
        button.innerHTML = previousHtml;
        if (previousTitle) button.setAttribute('title', previousTitle); else button.removeAttribute('title');
        if (previousAria) button.setAttribute('aria-label', previousAria); else button.removeAttribute('aria-label');
      }
      showInlineNotice('Не удалось изменить статус. Попробуйте ещё раз.');
    }
  });
});

/* v138: global CRM select/date controls */
document.addEventListener('DOMContentLoaded', () => {
  const padDatePart = value => String(value).padStart(2, '0');
  const toIsoDateGlobal = date => `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())}`;
  const parseIsoDateGlobal = value => {
    const parts = String(value || '').split('-').map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return new Date();
    return new Date(parts[0], parts[1] - 1, parts[2]);
  };
  const prettyDateGlobal = value => {
    if (!value) return '';
    const date = parseIsoDateGlobal(value);
    return `${padDatePart(date.getDate())}.${padDatePart(date.getMonth() + 1)}.${date.getFullYear()}`;
  };

  const ensureGlobalDateModal = () => {
    let modal = document.querySelector('.js-global-date-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'assignment-date-modal-overlay global-date-modal-overlay js-global-date-modal d-none';
    modal.innerHTML = `
      <div class="assignment-date-modal global-date-modal" role="dialog" aria-modal="true" aria-labelledby="global-date-modal-title">
        <div class="assignment-date-modal-head">
          <div>
            <div class="assignment-date-modal-kicker js-global-date-kicker">Дата</div>
            <h2 id="global-date-modal-title">Выбор даты</h2>
          </div>
          <button class="assignment-date-modal-close js-global-date-cancel" type="button" aria-label="Закрыть"><i class="bi bi-x-lg"></i></button>
        </div>
        <div class="assignment-date-quick-row">
          <button type="button" class="js-global-date-quick" data-offset="0">Сегодня</button>
          <button type="button" class="js-global-date-quick" data-offset="1">Завтра</button>
          <button type="button" class="js-global-date-quick" data-offset="-1">Вчера</button>
        </div>
        <div class="assignment-date-calendar">
          <div class="assignment-date-calendar-head">
            <button type="button" class="assignment-date-nav js-global-date-prev" aria-label="Предыдущий месяц"><i class="bi bi-chevron-left"></i></button>
            <div class="assignment-date-month js-global-date-month"></div>
            <button type="button" class="assignment-date-nav js-global-date-next" aria-label="Следующий месяц"><i class="bi bi-chevron-right"></i></button>
          </div>
          <div class="assignment-date-weekdays"><span>Пн</span><span>Вт</span><span>Ср</span><span>Чт</span><span>Пт</span><span>Сб</span><span>Вс</span></div>
          <div class="assignment-date-grid js-global-date-grid"></div>
        </div>
        <div class="assignment-date-selected">
          <span>Выбрано</span>
          <b class="js-global-date-selected-text"></b>
        </div>
        <div class="assignment-date-modal-actions">
          <button class="btn btn-outline-secondary js-global-date-cancel" type="button">Отмена</button>
          <button class="btn btn-primary js-global-date-save" type="button"><i class="bi bi-check2"></i><span>Выбрать дату</span></button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    return modal;
  };

  const openGlobalDateModal = (picker) => {
    const input = picker.querySelector('input[type="date"]');
    const button = picker.querySelector('.global-date-button');
    const valueText = picker.querySelector('.global-date-value');
    if (!input || !button || !valueText) return;

    const modal = ensureGlobalDateModal();
    const label = picker.dataset.dateLabel || getReadableDateLabel(input);
    modal.querySelector('.js-global-date-kicker').textContent = label;

    let selectedIso = input.value || toIsoDateGlobal(new Date());
    let viewDate = parseIsoDateGlobal(selectedIso);
    viewDate.setDate(1);

    const monthEl = modal.querySelector('.js-global-date-month');
    const gridEl = modal.querySelector('.js-global-date-grid');
    const selectedEl = modal.querySelector('.js-global-date-selected-text');
    const saveBtn = modal.querySelector('.js-global-date-save');

    const render = () => {
      const monthLabel = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(viewDate);
      monthEl.textContent = monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1);
      selectedEl.textContent = prettyDateGlobal(selectedIso);
      gridEl.innerHTML = '';

      const year = viewDate.getFullYear();
      const month = viewDate.getMonth();
      const first = new Date(year, month, 1);
      const firstWeekDay = (first.getDay() + 6) % 7;
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const todayIso = toIsoDateGlobal(new Date());

      for (let i = 0; i < firstWeekDay; i += 1) {
        const spacer = document.createElement('span');
        spacer.className = 'assignment-date-day-spacer';
        gridEl.appendChild(spacer);
      }
      for (let day = 1; day <= daysInMonth; day += 1) {
        const date = new Date(year, month, day);
        const iso = toIsoDateGlobal(date);
        const dayButton = document.createElement('button');
        dayButton.type = 'button';
        dayButton.className = 'assignment-date-day';
        dayButton.textContent = String(day);
        dayButton.classList.toggle('is-selected', iso === selectedIso);
        dayButton.classList.toggle('is-today', iso === todayIso);
        dayButton.addEventListener('click', () => {
          selectedIso = iso;
          render();
        });
        gridEl.appendChild(dayButton);
      }
    };

    const close = () => {
      modal.classList.add('d-none');
      document.removeEventListener('keydown', onKeydown);
    };
    const onKeydown = event => {
      if (event.key === 'Escape') close();
    };

    modal.querySelectorAll('.js-global-date-cancel').forEach(cancel => { cancel.onclick = close; });
    modal.querySelector('.js-global-date-prev').onclick = () => {
      viewDate.setMonth(viewDate.getMonth() - 1);
      render();
    };
    modal.querySelector('.js-global-date-next').onclick = () => {
      viewDate.setMonth(viewDate.getMonth() + 1);
      render();
    };
    modal.querySelectorAll('.js-global-date-quick').forEach(quick => {
      quick.onclick = () => {
        const next = new Date();
        next.setDate(next.getDate() + Number(quick.dataset.offset || 0));
        selectedIso = toIsoDateGlobal(next);
        viewDate = parseIsoDateGlobal(selectedIso);
        viewDate.setDate(1);
        render();
      };
    });
    modal.onclick = event => { if (event.target === modal) close(); };
    saveBtn.onclick = () => {
      input.value = selectedIso;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      valueText.textContent = prettyDateGlobal(selectedIso) || input.placeholder || 'Выберите дату';
      button.classList.toggle('is-empty', !input.value);
      close();
    };

    render();
    document.addEventListener('keydown', onKeydown);
    modal.classList.remove('d-none');
  };

  const readableDateNames = {
    planned_date: 'Дата выполнения',
    issued_day: 'День',
    report_date: 'Дата отчета',
    date: 'Дата',
    day: 'День',
    start_date: 'Дата начала',
    end_date: 'Дата окончания',
    inspection_date: 'Дата осмотра',
    completed_date: 'Дата выполнения',
    completion_date: 'Дата выполнения',
    task_date: 'Дата задачи',
  };

  const normalizeDateName = value => String(value || '').replace(/\[.*?\]/g, '').replace(/_\d+$/g, '').trim();

  const labelFromNearbyMarkup = input => {
    const safeId = input.id && window.CSS?.escape ? CSS.escape(input.id) : '';
    if (safeId) {
      const explicit = document.querySelector(`label[for="${safeId}"]`);
      if (explicit?.textContent?.trim()) return explicit.textContent.trim();
    }

    const labelledBy = input.getAttribute('aria-labelledby');
    if (labelledBy) {
      const text = labelledBy.split(/\s+/).map(id => document.getElementById(id)?.textContent?.trim()).filter(Boolean).join(' ');
      if (text) return text;
    }

    let node = input.parentElement;
    for (let depth = 0; node && depth < 4; depth += 1, node = node.parentElement) {
      const children = Array.from(node.children || []);
      const directLabel = children.find(child => child.tagName === 'LABEL' && child.textContent?.trim());
      if (directLabel) return directLabel.textContent.trim();
      const formLabel = children.find(child => child.classList?.contains('form-label') && child.textContent?.trim());
      if (formLabel) return formLabel.textContent.trim();
    }
    return '';
  };

  const getReadableDateLabel = input => {
    const nearby = labelFromNearbyMarkup(input);
    if (nearby) return nearby;

    const aria = input.getAttribute('aria-label');
    const normalizedAria = normalizeDateName(aria);
    if (aria && !readableDateNames[normalizedAria] && !aria.includes('_')) return aria;

    const normalizedName = normalizeDateName(input.name || input.id || '');
    if (readableDateNames[normalizedName]) return readableDateNames[normalizedName];
    if (normalizedName.startsWith('planned_date')) return readableDateNames.planned_date;
    if (normalizedName.endsWith('_date')) return 'Дата';
    return 'Дата';
  };

  const enhanceDateInput = input => {
    if (!input || input.dataset.globalDateReady === '1') return;
    if (input.closest('.assignment-report-date-picker')) return;
    if (input.closest('.global-date-picker')) return;
    if (input.matches('[data-native-date], [data-no-custom-date]')) return;

    input.dataset.globalDateReady = '1';
    const wrapper = document.createElement('div');
    wrapper.className = 'global-date-picker js-global-date-picker';
    wrapper.dataset.dateLabel = getReadableDateLabel(input);

    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);
    input.classList.add('global-native-date-input');
    input.tabIndex = -1;
    input.setAttribute('aria-hidden', 'true');

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'global-date-button';
    if (input.disabled) button.disabled = true;
    const initialText = prettyDateGlobal(input.value) || input.placeholder || 'Выберите дату';
    button.innerHTML = `<span class="global-date-value">${initialText}</span><span class="global-date-icon" aria-hidden="true"><i class="bi bi-calendar3"></i></span>`;
    button.classList.toggle('is-empty', !input.value);
    wrapper.appendChild(button);

    button.addEventListener('click', event => {
      event.preventDefault();
      if (!input.disabled && !input.readOnly) openGlobalDateModal(wrapper);
    });

    input.addEventListener('change', () => {
      const valueText = wrapper.querySelector('.global-date-value');
      if (valueText) valueText.textContent = prettyDateGlobal(input.value) || input.placeholder || 'Выберите дату';
      button.classList.toggle('is-empty', !input.value);
      button.disabled = input.disabled;
    });
  };

  const enhanceAllDateInputs = (scope = document) => {
    scope.querySelectorAll('input[type="date"]').forEach(enhanceDateInput);
  };

  enhanceAllDateInputs();

  const dateObserver = new MutationObserver(mutations => {
    mutations.forEach(mutation => {
      mutation.addedNodes.forEach(node => {
        if (node.nodeType !== 1) return;
        if (node.matches?.('input[type="date"]')) enhanceDateInput(node);
        node.querySelectorAll?.('input[type="date"]').forEach(enhanceDateInput);
      });
    });
  });
  dateObserver.observe(document.body, { childList: true, subtree: true });
});

const initSiteErrorCloseForms = (scope = document) => {
  const forms = [];
  if (scope.matches?.('form[action*="/site-errors/"][action$="/close"]')) forms.push(scope);
  scope.querySelectorAll?.('form[action*="/site-errors/"][action$="/close"]').forEach(form => forms.push(form));
  forms.forEach(form => {
    if (form.dataset.asyncBound === '1') return;
    form.dataset.asyncBound = '1';
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.submitter || form.querySelector('button[type="submit"]');
      const card = form.closest('.site-error-card');
      const stateBadge = card?.querySelector('.site-error-state-badge');
      const isRegistration = button?.textContent?.includes('Принять') || Boolean(card?.querySelector('.badge.bg-success'));
      const previousHtml = button?.innerHTML || '';
      if (button) button.disabled = true;
      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) throw new Error(data.message || 'Не удалось обновить статус');
        const isClosed = data.status === 'closed';
        card?.classList.toggle('closed', isClosed);
        card?.classList.toggle('site-error-card-open', !isClosed);
        card?.classList.toggle('site-error-card-accepted', isClosed && isRegistration);
        if (stateBadge) {
          stateBadge.className = `badge site-error-state-badge ${isClosed ? (isRegistration ? 'site-error-state-accepted' : 'site-error-state-closed') : 'site-error-state-new'}`;
          stateBadge.textContent = isClosed ? (isRegistration ? 'Принята' : 'Закрыта') : 'Новая';
        }
        if (button) {
          button.className = `btn btn-sm site-error-action-btn ${isClosed || isRegistration ? 'site-error-action-btn-success' : 'site-error-action-btn-close'}`;
          button.textContent = isClosed ? 'Вернуть в новые' : (isRegistration ? 'Принять' : 'Закрыть ошибку');
        }
        showCrmNotice(data.message || 'Статус ошибки обновлен', 'success');
      } catch (error) {
        showCrmNotice(error.message || 'Не удалось обновить статус', 'danger');
      } finally {
        if (button) {
          button.disabled = false;
          if (previousHtml && !button.innerHTML) button.innerHTML = previousHtml;
        }
      }
    });
  });
};

document.addEventListener('DOMContentLoaded', () => initSiteErrorCloseForms(document));
document.addEventListener('crm:ajax-pagination-updated', event => {
  if (['site-errors', 'developer-tools'].includes(event.detail?.pageKey)) {
    initSiteErrorCloseForms(event.detail?.content || document);
  }
});

document.addEventListener('DOMContentLoaded', () => {
  const hasInitialPicker = Boolean(document.querySelector('.js-developer-stat-range-picker'));
  const supportsPartialDeveloperTabs = document.documentElement.classList.contains('desktop-like-pointer');
  if (!hasInitialPicker && !supportsPartialDeveloperTabs) return;

  const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
  const padDatePart = value => String(value).padStart(2, '0');
  const todayDate = new Date();
  const todayIso = `${todayDate.getFullYear()}-${padDatePart(todayDate.getMonth() + 1)}-${padDatePart(todayDate.getDate())}`;
  const toIsoDate = date => `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())}`;

  const parseIsoDate = value => {
    if (!value) return null;
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return null;
    const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    return Number.isNaN(date.getTime()) ? null : date;
  };

  const prettyDate = value => {
    const date = parseIsoDate(value);
    if (!date) return '';
    return `${padDatePart(date.getDate())}.${padDatePart(date.getMonth() + 1)}.${date.getFullYear()}`;
  };

  const normalizeRange = (start, end, maxIso) => {
    let safeStart = start || end || maxIso || todayIso;
    let safeEnd = end || start || safeStart;
    if (maxIso && safeStart > maxIso) safeStart = maxIso;
    if (maxIso && safeEnd > maxIso) safeEnd = maxIso;
    if (safeStart > safeEnd) [safeStart, safeEnd] = [safeEnd, safeStart];
    return { start: safeStart, end: safeEnd };
  };

  const formatRange = (start, end) => {
    if (!start && !end) return 'Выберите период';
    const finalEnd = end || start;
    if (start === finalEnd) return prettyDate(start);
    return `${prettyDate(start)} - ${prettyDate(finalEnd)}`;
  };

  const shiftIsoDate = (iso, offset) => {
    const base = parseIsoDate(iso) || parseIsoDate(todayIso) || new Date();
    base.setDate(base.getDate() + offset);
    return toIsoDate(base);
  };

  let modal = document.querySelector('.js-developer-stat-range-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.className = 'assignment-date-modal-overlay js-developer-stat-range-modal d-none';
    modal.innerHTML = `
      <div class="assignment-date-modal developer-stat-range-modal" role="dialog" aria-modal="true" aria-labelledby="developer-stat-range-modal-title">
        <div class="assignment-date-modal-head">
          <div>
            <h2 id="developer-stat-range-modal-title">Выбор периода</h2>
          </div>
          <button class="assignment-date-modal-close js-developer-stat-range-cancel" type="button" aria-label="Закрыть"><i class="bi bi-x-lg"></i></button>
        </div>
        <div class="assignment-date-quick-row">
          <button type="button" class="js-developer-stat-range-quick" data-days="7">7 дней</button>
          <button type="button" class="js-developer-stat-range-quick" data-days="14">14 дней</button>
          <button type="button" class="js-developer-stat-range-quick" data-days="30">30 дней</button>
        </div>
        <div class="assignment-date-calendar">
          <div class="assignment-date-calendar-head">
            <button type="button" class="assignment-date-nav js-developer-stat-range-prev" aria-label="Предыдущий месяц"><i class="bi bi-chevron-left"></i></button>
            <div class="assignment-date-month js-developer-stat-range-month"></div>
            <button type="button" class="assignment-date-nav js-developer-stat-range-next" aria-label="Следующий месяц"><i class="bi bi-chevron-right"></i></button>
          </div>
          <div class="assignment-date-weekdays"><span>Пн</span><span>Вт</span><span>Ср</span><span>Чт</span><span>Пт</span><span>Сб</span><span>Вс</span></div>
          <div class="assignment-date-grid js-developer-stat-range-grid"></div>
        </div>
        <div class="assignment-date-modal-actions">
          <button class="btn btn-outline-secondary js-developer-stat-range-cancel" type="button">Отмена</button>
          <button class="btn btn-primary js-developer-stat-range-save" type="button"><i class="bi bi-check2"></i><span>Показать статистику</span></button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  }

  const monthEl = modal.querySelector('.js-developer-stat-range-month');
  const gridEl = modal.querySelector('.js-developer-stat-range-grid');
  const saveBtn = modal.querySelector('.js-developer-stat-range-save');

  let activePicker = null;
  let viewDate = new Date();
  let draftStart = '';
  let draftEnd = '';

  const onKeydown = event => {
    if (event.key === 'Escape') close();
  };

  const close = () => {
    document.removeEventListener('keydown', onKeydown);
    modal.classList.add('d-none');
    activePicker = null;
  };

  const renderSelectedState = () => {
    if (!draftStart) {
      saveBtn.disabled = true;
      return;
    }
    saveBtn.disabled = false;
  };

  const renderCalendar = () => {
    if (!activePicker) return;
    const year = viewDate.getFullYear();
    const month = viewDate.getMonth();
    const maxIso = activePicker.maxIso || '';
    const actualRange = draftStart && draftEnd ? normalizeRange(draftStart, draftEnd, maxIso) : null;

    monthEl.textContent = `${monthNames[month]} ${year}`;
    gridEl.innerHTML = '';

    const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7;
    for (let index = 0; index < firstWeekday; index += 1) {
      const spacer = document.createElement('span');
      spacer.className = 'assignment-date-day-spacer';
      gridEl.appendChild(spacer);
    }

    const daysInMonth = new Date(year, month + 1, 0).getDate();
    for (let day = 1; day <= daysInMonth; day += 1) {
      const date = new Date(year, month, day);
      const iso = toIsoDate(date);
      const button = document.createElement('button');
      const isDisabled = maxIso && iso > maxIso;
      button.type = 'button';
      button.className = 'assignment-date-day';
      button.textContent = String(day);
      button.dataset.iso = iso;
      button.setAttribute('aria-label', prettyDate(iso) || iso);
      button.disabled = isDisabled;
      if (iso === todayIso) button.classList.add('is-today');
      if (draftStart && iso === draftStart) button.classList.add('is-selected');
      if (draftEnd && iso === draftEnd) button.classList.add('is-selected');
      if (actualRange && iso > actualRange.start && iso < actualRange.end) button.classList.add('is-in-range');

      button.addEventListener('click', () => {
        if (!draftStart || draftEnd) {
          draftStart = iso;
          draftEnd = '';
        } else {
          const resolved = normalizeRange(draftStart, iso, maxIso);
          draftStart = resolved.start;
          draftEnd = resolved.end;
        }
        renderCalendar();
      });

      gridEl.appendChild(button);
    }

    renderSelectedState();
  };

  modal.querySelectorAll('.js-developer-stat-range-cancel').forEach(button => {
    button.addEventListener('click', close);
  });
  modal.querySelector('.js-developer-stat-range-prev').addEventListener('click', () => {
    viewDate.setMonth(viewDate.getMonth() - 1);
    renderCalendar();
  });
  modal.querySelector('.js-developer-stat-range-next').addEventListener('click', () => {
    viewDate.setMonth(viewDate.getMonth() + 1);
    renderCalendar();
  });
  modal.querySelectorAll('.js-developer-stat-range-quick').forEach(button => {
    button.addEventListener('click', () => {
      const days = Number(button.dataset.days || 1);
      const anchorIso = activePicker?.maxIso || todayIso;
      draftEnd = anchorIso;
      draftStart = shiftIsoDate(anchorIso, -(days - 1));
      viewDate = parseIsoDate(draftStart) || new Date();
      viewDate.setDate(1);
      renderCalendar();
    });
  });
  modal.addEventListener('click', event => {
    if (event.target === modal) close();
  });
  saveBtn.addEventListener('click', () => {
    if (!activePicker || !draftStart) return;
    const resolved = normalizeRange(draftStart, draftEnd || draftStart, activePicker.maxIso || '');
    activePicker.startInput.value = resolved.start;
    activePicker.endInput.value = resolved.end;
    activePicker.valueEl.textContent = formatRange(resolved.start, resolved.end);
    const form = activePicker.form;
    close();
    if (!form) return;
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });

  const open = picker => {
    const startInput = picker.querySelector('input[name="start_date"]');
    const endInput = picker.querySelector('input[name="end_date"]');
    const maxIso = picker.dataset.maxDate || '';
    const resolved = normalizeRange(startInput?.value || picker.dataset.startDate, endInput?.value || picker.dataset.endDate, maxIso);

    activePicker = {
      form: picker.closest('form'),
      startInput,
      endInput,
      maxIso,
      valueEl: picker.querySelector('.js-developer-stat-range-value'),
    };
    draftStart = resolved.start;
    draftEnd = resolved.end;
    viewDate = parseIsoDate(resolved.start || resolved.end || maxIso) || new Date();
    viewDate.setDate(1);

    renderCalendar();
    document.addEventListener('keydown', onKeydown);
    modal.classList.remove('d-none');
  };

  document.addEventListener('click', event => {
    const openButton = event.target.closest('.js-developer-stat-range-open');
    if (!openButton) return;
    const picker = openButton.closest('.js-developer-stat-range-picker');
    if (!picker) return;
    event.preventDefault();
    open(picker);
  });
});


document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form[data-task-comment-async="1"]').forEach(form => {
    if (form.dataset.taskCommentBound === '1') return;
    form.dataset.taskCommentBound = '1';
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
      const previousText = button?.tagName === 'INPUT' ? button.value : (button?.innerHTML || '');
      if (button) button.disabled = true;
      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) throw new Error(data.message || 'Не удалось добавить комментарий');
        const commentsCard = form.closest('.card-body');
        const emptyComment = commentsCard?.querySelector('.text-muted');
        if (emptyComment && !commentsCard.querySelector('.comment-item')) emptyComment.remove();
        if (commentsCard && data.comment) {
          const item = document.createElement('div');
          item.className = 'comment-item mb-2';
          item.innerHTML = '<div class="comment-meta">' + escapeHtml(data.comment.author || '') + ' · ' + escapeHtml(data.comment.timestamp || '') + '</div><div class="comment-body">' + escapeHtml(data.comment.body || '') + '</div>';
          form.before(item);
        }
        const textarea = form.querySelector('textarea');
        if (textarea) textarea.value = '';
        appendTimelineEntry(document.querySelector('[data-task-history-list]'), document.querySelector('[data-task-history-empty]'), data.history_entry);
        showCrmNotice(data.message || 'Комментарий добавлен', 'success');
      } catch (error) {
        showCrmNotice(error.message || 'Не удалось добавить комментарий', 'danger');
      } finally {
        if (button) {
          button.disabled = false;
          if (button.tagName === 'INPUT') button.value = previousText;
          else button.innerHTML = previousText;
        }
      }
    });
  });
});


const initDeveloperIpToggles = (scope = document) => {
  const toggles = scope.querySelectorAll('.js-developer-ip-toggle');
  if (!toggles.length) return;

  const updateHash = rowId => {
    const url = new URL(window.location.href);
    url.searchParams.delete('ip');
    url.hash = rowId ? rowId : '';
    window.history.replaceState({}, '', url.toString());
  };

  const setExpanded = (item, expanded) => {
    if (!item) return;
    const button = item.querySelector('.js-developer-ip-toggle');
    const details = item.querySelector('.developer-ip-inline-details');
    item.classList.toggle('is-expanded', expanded);
    if (button) {
      button.classList.toggle('is-active', expanded);
      button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }
    if (details) details.classList.toggle('d-none', !expanded);
  };

  const collapseSiblings = currentItem => {
    const list = currentItem?.closest('.developer-ranked-list');
    if (!list) return;
    list.querySelectorAll('.developer-ip-item.is-expanded').forEach(item => {
      if (item !== currentItem) setExpanded(item, false);
    });
  };

  toggles.forEach(button => {
    if (button.dataset.developerIpBound === '1') return;
    button.addEventListener('click', event => {
      event.preventDefault();
      const rowId = button.dataset.ipRow || '';
      const item = rowId ? document.getElementById(rowId) : button.closest('.developer-ip-item');
      if (!item) return;
      const shouldExpand = !item.classList.contains('is-expanded');
      collapseSiblings(item);
      setExpanded(item, shouldExpand);
      updateHash(shouldExpand ? item.id : '');
    });
    button.dataset.developerIpBound = '1';
  });

  const hashId = decodeURIComponent((window.location.hash || '').replace(/^#/, ''));
  if (hashId) {
    const hashedItem = document.getElementById(hashId);
    if (hashedItem?.classList.contains('developer-ip-item')) {
      collapseSiblings(hashedItem);
      setExpanded(hashedItem, true);
    }
  }
};

document.addEventListener('DOMContentLoaded', () => initDeveloperIpToggles(document));
document.addEventListener('crm:ajax-pagination-updated', event => {
  if (['developer-statistics', 'developer-tools'].includes(event.detail?.pageKey)) {
    initDeveloperIpToggles(event.detail?.content || document);
  }
});

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-project-access-control]').forEach(control => {
    const projectInputs = [...control.querySelectorAll('input[name="project_ids"]')];
    const label = control.querySelector('[data-project-access-label]');
    const autosaveForm = control.querySelector('.users-project-autosave');
    if (!projectInputs.length) return;

    const projectCountLabel = count => {
      if (count === 1) return '1 объект';
      if (count >= 2 && count <= 4) return `${count} объекта`;
      return `${count} объектов`;
    };

    const syncAccessControl = () => {
      if (label) {
        const selectedCount = projectInputs.filter(input => input.checked).length;
        label.textContent = projectCountLabel(selectedCount);
      }
    };

    let savedIds = new Set(projectInputs.filter(input => input.checked).map(input => input.value));
    const restoreSavedProjects = () => {
      projectInputs.forEach(input => { input.checked = savedIds.has(input.value); });
      syncAccessControl();
    };

    projectInputs.forEach(input => input.addEventListener('change', async () => {
      syncAccessControl();
      if (!autosaveForm) return;
      if (!projectInputs.some(projectInput => projectInput.checked)) {
        restoreSavedProjects();
        window.showCrmNotice?.('Выберите хотя бы один объект.', 'warning');
        return;
      }

      const formData = new FormData(autosaveForm);
      projectInputs.forEach(projectInput => { projectInput.disabled = true; });
      control.classList.add('is-saving');
      try {
        const response = await fetch(autosaveForm.action, {
          method: 'POST',
          body: formData,
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) throw new Error(data.message || 'Не удалось сохранить доступ');
        savedIds = new Set((data.project_ids || []).map(String));
        restoreSavedProjects();
        if (label && data.label) label.textContent = data.label;
        control.classList.add('is-saved');
        window.setTimeout(() => control.classList.remove('is-saved'), 900);
      } catch (error) {
        restoreSavedProjects();
        window.showCrmNotice?.(error.message || 'Не удалось сохранить доступ к объектам', 'danger');
      } finally {
        projectInputs.forEach(projectInput => { projectInput.disabled = false; });
        control.classList.remove('is-saving');
      }
    }));
    syncAccessControl();
  });

  document.querySelectorAll('.users-name-autosave').forEach(form => {
    const input = form.querySelector('.users-name-input');
    if (!input) return;
    let savedValue = form.dataset.savedValue || '';
    let saving = false;

    const saveName = async () => {
      const requestedValue = input.value.trim();
      if (saving || requestedValue === savedValue) {
        input.value = requestedValue;
        return;
      }
      saving = true;
      input.disabled = true;
      form.classList.add('is-saving');
      try {
        const formData = new FormData(form);
        formData.set('full_name', requestedValue);
        const response = await fetch(form.action, {
          method: 'POST',
          body: formData,
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) throw new Error(data.message || 'Не удалось сохранить имя');
        savedValue = data.full_name ?? requestedValue;
        form.dataset.savedValue = savedValue;
        input.value = savedValue;
        form.classList.add('is-saved');
        window.setTimeout(() => form.classList.remove('is-saved'), 900);
      } catch (error) {
        input.value = savedValue;
        window.showCrmNotice?.(error.message || 'Не удалось сохранить имя', 'danger');
      } finally {
        saving = false;
        input.disabled = false;
        form.classList.remove('is-saving');
      }
    };

    form.addEventListener('submit', event => {
      event.preventDefault();
      input.blur();
    });
    input.addEventListener('blur', saveName);
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        input.blur();
      } else if (event.key === 'Escape') {
        input.value = savedValue;
        input.blur();
      }
    });
  });
});

document.addEventListener('DOMContentLoaded', () => {
  const isDesktopWeb = window.matchMedia?.('(hover: hover) and (pointer: fine)').matches
    && !window.matchMedia?.('(display-mode: standalone)').matches
    && !window.navigator.standalone;
  if (!isDesktopWeb) return;

  const removeDesktopHoverTitles = root => {
    root.querySelectorAll?.('.remarks-tab-link-category[title], .materials-filter-icon-btn[title]').forEach(el => {
      el.removeAttribute('title');
    });
  };

  removeDesktopHoverTitles(document);
  new MutationObserver(mutations => {
    mutations.forEach(mutation => {
      mutation.addedNodes.forEach(node => {
        if (node.nodeType === Node.ELEMENT_NODE) removeDesktopHoverTitles(node);
      });
    });
  }).observe(document.body, { childList: true, subtree: true });
});

/* Mobile category buttons show their full label for exactly one second before
   the existing AJAX/navigation handler continues. */
(() => {
  const labelTimers = new WeakMap();
  const resumedLinks = new WeakSet();
  const isMobileRemarks = () => window.matchMedia?.('(max-width: 767.98px)').matches
    && document.body?.classList.contains('app-body');

  const showLabel = (link, onFinish = null) => {
    const previousTimer = labelTimers.get(link);
    if (previousTimer) window.clearTimeout(previousTimer);
    document.querySelectorAll('.remarks-tab-link-category.is-mobile-label-visible').forEach(item => {
      if (item !== link) item.classList.remove('is-mobile-label-visible');
    });
    link.classList.add('is-mobile-label-visible');
    const timer = window.setTimeout(() => {
      link.classList.remove('is-mobile-label-visible');
      labelTimers.delete(link);
      onFinish?.();
    }, 1000);
    labelTimers.set(link, timer);
  };

  document.addEventListener('pointerdown', event => {
    if (!isMobileRemarks()) return;
    const link = event.target.closest?.('.remarks-tab-link-category[data-category-label]');
    if (link) showLabel(link);
  }, true);

  document.addEventListener('click', event => {
    if (!isMobileRemarks() || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest?.('.remarks-tab-link-category[data-category-label]');
    if (!link || resumedLinks.has(link)) {
      if (link) resumedLinks.delete(link);
      return;
    }
    const href = link.getAttribute('href');
    if (!href || href === '#') return;
    event.preventDefault();
    event.stopImmediatePropagation();
    showLabel(link, () => {
      resumedLinks.add(link);
      link.click();
    });
  }, true);
})();
