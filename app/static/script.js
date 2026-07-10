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
const getDesktopReferenceWidth = () => DESKTOP_REFERENCE_WIDTH;
const getDesktopStageScale = () => Math.min(1, getViewportWidth() / DESKTOP_REFERENCE_WIDTH);
const shouldAllowAdaptiveMobileViewport = () => false;
const isAdaptiveMobileViewport = () => shouldAllowAdaptiveMobileViewport() && !isTouchAppDevice() && getViewportWidth() <= DESKTOP_TO_MOBILE_VIEWPORT_WIDTH;
const isTouchMobileViewport = () => isPhoneTouchDevice();
const isMobileViewport = () => isTouchMobileViewport() || isAdaptiveMobileViewport();
const isDesktopLikePointer = () => !isTouchAppDevice() && !isAdaptiveMobileViewport();
const shouldUseDesktopViewportLock = () => isDesktopLikePointer();
const normalizeConfirmText = (text) => (text || '').replace(/\\n/g, '\n').replace(/\\t/g, '\t');
let desktopViewportSyncUnlocked = document.readyState === 'complete';

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
  const mobileDevLoaders = document.querySelectorAll('.mobile-dev-screen.site-page-loader');
  const suppressStaticCrmLoaders = (forceDisplayNone = false) => {
    document.documentElement.classList.add('crm-loader-suppressed');
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
    return;
  }
  const startedAt = Date.now();
  const minVisibleMs = 2300;
  const hide = () => {
    const delay = Math.max(0, minVisibleMs - (Date.now() - startedAt));
    window.setTimeout(() => {
      loaders.forEach(loader => loader.classList.add('is-hidden'));
      hideMobileDevLoaders(true);
    }, delay);
  };
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

document.addEventListener('DOMContentLoaded', () => {
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

  const syncAppViewportHeight = () => {
    if (!isIosDevice && !isMobileViewport()) return;
    const height = Math.round(window.visualViewport?.height || window.innerHeight || document.documentElement.clientHeight);
    if (height > 0) document.documentElement.style.setProperty('--app-height', `${height}px`);
  };

  const syncMobileViewportClass = () => {
    const mobileViewport = isMobileViewport();
    document.documentElement.classList.toggle('mobile-viewport', mobileViewport);
    document.body.classList.toggle('mobile-viewport', mobileViewport);
  };

  const syncMobileOrientationLockState = () => {
    const landscapeLocked = isTouchMobileViewport() && window.matchMedia('(orientation: landscape)').matches;
    document.documentElement.classList.toggle('mobile-landscape-locked', landscapeLocked);
    document.body.classList.toggle('mobile-landscape-locked', landscapeLocked);
  };

  const tryLockPortraitOrientation = () => {
    if (!isTouchMobileViewport()) return;
    if (!screen.orientation || typeof screen.orientation.lock !== 'function') return;
    screen.orientation.lock('portrait').catch(() => {});
  };

  const handleMobileViewportChange = () => {
    syncDesktopViewportLock();
    syncMobileViewportClass();
    syncMobileOrientationLockState();
    syncAppViewportHeight();
    tryLockPortraitOrientation();
  };

  if (isIosDevice) document.body.classList.add('ios-device');
  if (isCoarsePointer) document.body.classList.add('touch-device');
  if (isStandaloneApp) document.body.classList.add('standalone-app');
  if (isStandaloneApp) document.documentElement.classList.add('standalone-app');
  syncDesktopViewportLock({ force: true });
  syncMobileViewportClass();
  syncMobileOrientationLockState();
  if (document.querySelector('.mobile-project-topbar')) document.body.classList.add('has-mobile-project-topbar');
  if (document.querySelector('.account-page')) document.body.classList.add('has-account-page');
  syncAppViewportHeight();
  tryLockPortraitOrientation();
  if (mobileViewportMedia.addEventListener) {
    mobileViewportMedia.addEventListener('change', handleMobileViewportChange);
  } else if (mobileViewportMedia.addListener) {
    mobileViewportMedia.addListener(handleMobileViewportChange);
  }
  window.addEventListener('resize', syncDesktopViewportLock, { passive: true });
  window.addEventListener('resize', syncAppViewportHeight, { passive: true });
  window.addEventListener('resize', handleMobileViewportChange, { passive: true });
  window.visualViewport?.addEventListener('resize', syncDesktopViewportLock, { passive: true });
  window.visualViewport?.addEventListener('resize', syncAppViewportHeight, { passive: true });
  window.visualViewport?.addEventListener('resize', syncMobileOrientationLockState, { passive: true });
  window.visualViewport?.addEventListener('scroll', syncAppViewportHeight, { passive: true });
  window.addEventListener('orientationchange', () => {
    window.setTimeout(syncAppViewportHeight, 140);
    window.setTimeout(syncMobileOrientationLockState, 40);
    window.setTimeout(tryLockPortraitOrientation, 80);
  }, { passive: true });

  if (isIosDevice) {
    document.addEventListener('gesturestart', event => event.preventDefault(), { passive: false });
    document.addEventListener('gesturechange', event => event.preventDefault(), { passive: false });
    document.addEventListener('gestureend', event => event.preventDefault(), { passive: false });
  }
  const themeColorMeta = document.querySelector('meta[name="theme-color"]');
  const msTileColorMeta = document.querySelector('meta[name="msapplication-TileColor"]');
  const defaultThemeColor = themeColorMeta?.getAttribute('content') || '#8dd62c';
  const authThemeColor = '#ffffff';
  const appTopbarThemeColor = '#1f2730';

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
    customSelectBootRoot.classList.remove('crm-custom-select-pending');
    customSelectBootRoot.classList.add('crm-custom-select-ready');
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
    // Mobile now uses the same custom select UI as desktop for visual consistency.
    const useNativeMobileSelect = false;

    scope.querySelectorAll('select').forEach(select => {
      if (select.matches(excludedSelector)) return;
      if (select.closest('.developer-custom-select')) return;
      if (select.dataset.customSelectReady === '1') return;

      if (useNativeMobileSelect && !select.matches('[data-force-custom-select]')) {
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

    scope.querySelectorAll('.js-developer-custom-select').forEach(selectShell => {
      const select = selectShell.querySelector('select');
      if (!select || selectShell.querySelector('.developer-select-button')) return;

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
        const viewportGap = 12;
        const minWidth = Math.max(rect.width, 180);
        const availableBelow = Math.max(0, window.innerHeight - rect.bottom - viewportGap);
        const availableAbove = Math.max(0, rect.top - viewportGap);
        const estimatedHeight = Math.min(300, Math.max(46, options.length * 42 + 18));
        const measuredHeight = menu.scrollHeight ? Math.min(300, Math.max(46, menu.scrollHeight)) : estimatedHeight;
        // Выпадающий список по умолчанию открываем вниз, чтобы он не налезал на поле и кнопки сверху.
        // Вверх открываем только когда снизу совсем мало места, иначе ограничиваем высоту и даем прокрутку.
        const openAbove = availableBelow < 96 && availableAbove > availableBelow + 80;
        const available = Math.max(96, (openAbove ? availableAbove : availableBelow) - 8);
        const maxHeight = Math.max(96, Math.min(300, available));
        const menuHeight = Math.min(measuredHeight, maxHeight);
        const left = Math.min(Math.max(viewportGap, rect.left), Math.max(viewportGap, window.innerWidth - minWidth - viewportGap));
        const top = openAbove
          ? Math.max(viewportGap, rect.top - menuHeight - 8)
          : Math.max(viewportGap, Math.min(window.innerHeight - viewportGap - menuHeight, rect.bottom + 8));
        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
        menu.style.width = `${minWidth}px`;
        menu.style.maxHeight = `${maxHeight}px`;
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

  initDeveloperCustomSelects();
  finishCustomSelectBoot();

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
          initDeveloperCustomSelects(node.matches?.('select') ? node.parentElement || document : node);
        }
      });
    });
  });
  customSelectObserver.observe(document.body, { childList: true, subtree: true });

  const initTooltips = () => {
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
  const canShowViewportTransitionLoader = () => (
    Boolean(viewportTransitionLoader)
    && isTouchAppDevice()
    && !document.documentElement.classList.contains('crm-loader-suppressed')
  );

  const showViewportTransitionLoader = () => {
    if (!canShowViewportTransitionLoader()) return;
    viewportTransitionLoader.style.removeProperty('display');
    viewportTransitionLoader.style.pointerEvents = 'auto';
    viewportTransitionLoader.classList.remove('is-hidden');
  };

  const navigateWithViewportTransition = href => {
    if (!href) return;
    showViewportTransitionLoader();
    window.location.href = href;
  };

  document.addEventListener('click', event => {
    if (!canShowViewportTransitionLoader()) return;
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
      showViewportTransitionLoader();
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
            <button class="btn btn-outline-secondary js-assignment-confirm-cancel" type="button">Отмена</button>
            <button class="btn btn-danger js-assignment-confirm-ok" type="button">Подтвердить</button>
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
    item.append(meta, summary);
    list.prepend(item);
    list.hidden = false;
    if (emptyNode) emptyNode.hidden = true;
  };

  const syncStatusActionVisibility = (root = document) => {
    root.querySelectorAll('.actions-cell[data-current-status]').forEach(actionsCell => {
      const currentStatus = actionsCell.dataset.currentStatus || '';
      actionsCell.querySelectorAll('.status-action-form[data-status-action]').forEach(actionForm => {
        const action = actionForm.dataset.statusAction || '';
        let shouldHide = action === currentStatus;
        if (action === 'done') shouldHide = currentStatus !== 'not_started';
        if (action === 'not_started') shouldHide = currentStatus !== 'done';
        actionForm.classList.toggle('d-none', shouldHide);
      });
    });
  };

  syncStatusActionVisibility();

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
        const resp = await fetch(form.action, {
          method: 'POST',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
          },
          body: new FormData(form),
        });
        const data = await resp.json().catch(() => null);
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

        if (form.dataset.apartmentStatusToggle !== undefined) {
          form.action = data.is_done ? (form.dataset.notStartedUrl || form.action) : (form.dataset.doneUrl || form.action);
        }

        const actionsCell = row?.querySelector('.actions-cell');
        if (actionsCell) {
          actionsCell.dataset.currentStatus = data.status || '';
        }
        syncStatusActionVisibility(row || document);

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
  const bulkStorage = (scope) => scope.dataset.selectionStorage === 'local' ? window.localStorage : window.sessionStorage;
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
    form.querySelectorAll('input.js-bulk-persisted-input[name="task_ids"]').forEach(input => input.remove());
    const visibleCheckIds = new Set(
      Array.from(scope.querySelectorAll('.js-bulk-check')).map(check => String(check.value || '')).filter(Boolean)
    );
    Array.from(scope.__bulkSelectedIds).forEach(taskId => {
      if (visibleCheckIds.has(String(taskId))) return;
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'task_ids';
      input.value = taskId;
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

  document.querySelectorAll('.js-bulk-selectable').forEach(scope => {
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
      checks.filter(isBulkCheckAvailable).forEach(check => {
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

    scope.querySelector('.js-bulk-master')?.addEventListener('change', event => {
      setAll(event.currentTarget.checked);
    });

    scope.querySelectorAll('.js-bulk-clear').forEach(button => {
      button.addEventListener('click', () => {
        if (scope.__bulkSelectedIds instanceof Set) {
          scope.__bulkSelectedIds.clear();
          checks.forEach(check => { check.checked = false; });
          writeBulkSelection(scope);
          syncBulkScope(scope);
          return;
        }
        setAll(false);
      });
    });

    checks.forEach(check => {
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
    });

    scope.querySelectorAll('.js-bulk-row').forEach(row => {
      let openTimer = null;
      row.addEventListener('click', event => {
        if (event.target.closest('a, button, input, textarea, select, label, [role="button"]')) return;
        if (scope.dataset.bulkRowClick === 'open') {
          const hasActiveSelection = checks.some(check => check.checked && !check.disabled);
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
    });

    syncBulkScope(scope);
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

  const refreshIssuedCountsAfterRemoval = (row) => {
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

  const markIssuedRowUnassigned = (row, payload = {}) => {
    if (!row) return;
    row.classList.add('assignment-issued-row-unassigned');
    row.dataset.unassigned = '1';
    renderIssuedDateCell(row.querySelector('.assignment-issued-date-cell'), payload);

    const statusButton = row.querySelector('.assignment-status-toggle');
    if (statusButton) {
      statusButton.textContent = 'Без исполнителя';
      statusButton.className = 'badge assignment-status-toggle bg-secondary';
      statusButton.disabled = true;
      statusButton.title = 'Исполнитель снят. После обновления таблицы задача исчезнет из выданных.';
    }

    row.querySelectorAll('.js-assignment-date-open').forEach(button => {
      button.disabled = true;
      button.title = 'Сначала назначьте исполнителя';
    });

    const unassignButton = row.querySelector('.js-assignment-unassign-direct, button[name="remove_assignee_task_id"]');
    if (unassignButton) {
      unassignButton.disabled = true;
      unassignButton.classList.add('is-unassigned');
      unassignButton.title = 'Исполнитель уже снят';
      const label = unassignButton.querySelector('.assignment-unassign-text');
      if (label) label.textContent = 'Снят';
    }

    const changeButton = row.querySelector('.js-assignment-change-assignee-open');
    if (changeButton) {
      changeButton.dataset.currentResponsibleId = '';
      changeButton.dataset.currentResponsibleName = '—';
    }
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
      const confirmed = await showCrmConfirm({
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
        } else if (submitter.name === 'remove_assignee_task_id') {
          markIssuedRowUnassigned(row, data);
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

  const changeAssigneeModal = document.getElementById('assignmentChangeAssigneeModal');
  if (changeAssigneeModal) {
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
  }

  document.querySelectorAll('.assignment-change-assignee-list input[name="new_responsible_id"]').forEach(input => {
    input.addEventListener('change', () => {
      const list = input.closest('.assignment-change-assignee-list');
      list?.querySelectorAll('.assignment-change-assignee-option').forEach(option => {
        const optionInput = option.querySelector('input[name="new_responsible_id"]');
        option.classList.toggle('is-picked', Boolean(optionInput?.checked));
      });
    });
  });

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
      } finally {
        saveBtn.disabled = false;
      }
    };

    render();
    document.addEventListener('keydown', onKeydown);
    modal.classList.remove('d-none');
  };

  document.querySelectorAll('.js-assignment-date-open').forEach(button => {
    button.addEventListener('click', event => {
      event.preventDefault();
      openAssignmentDateModal(button);
    });
  });

  const postNativeUnassign = (url, csrfToken) => {
    const form = document.createElement('form');
    form.method = 'post';
    form.action = url;
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'csrf_token';
    input.value = csrfToken || getCsrfToken();
    form.appendChild(input);
    document.body.appendChild(form);
    form.submit();
  };

  document.addEventListener('click', async event => {
    const button = event.target.closest('.js-assignment-unassign-direct');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    if (button.disabled || button.dataset.pending === '1') return;

    const confirmed = await showCrmConfirm({
      title: button.dataset.assignmentConfirmTitle || 'Снять исполнителя',
      message: button.dataset.assignmentConfirm || 'Снять исполнителя с этой задачи?',
      okText: button.dataset.assignmentConfirmOk || 'Снять',
      danger: true,
    });
    if (!confirmed) return;

    const url = button.dataset.unassignUrl;
    const csrfToken = button.closest('form')?.querySelector('input[name="csrf_token"]')?.value || getCsrfToken();
    if (!url) return;
    if (!window.fetch) {
      postNativeUnassign(url, csrfToken);
      return;
    }

    button.dataset.pending = '1';
    button.disabled = true;
    try {
      const body = new FormData();
      body.set('csrf_token', csrfToken);
      const response = await fetch(url, {
        method: 'POST',
        body,
        credentials: 'same-origin',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'application/json',
        },
      });
      const isJson = (response.headers.get('content-type') || '').includes('application/json');
      if (!isJson) {
        postNativeUnassign(url, csrfToken);
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) {
        showCrmNotice(data.message || 'Не удалось снять исполнителя', 'danger');
        button.disabled = false;
        return;
      }
      markIssuedRowUnassigned(button.closest('.assignment-issued-row'), data);
      showCrmNotice(data.message || 'Исполнитель снят', 'success');
    } catch (error) {
      showCrmNotice(error.message || 'Не удалось снять исполнителя', 'danger');
      button.disabled = false;
    } finally {
      delete button.dataset.pending;
    }
  }, true);

  document.addEventListener('click', event => {
    const submitter = event.target.closest('button[name="toggle_employee_status_task_id"], button[name="remove_assignee_task_id"]');
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
      table.querySelectorAll('tbody tr').forEach(row => {
        Array.from(row.children).forEach((cell, index) => {
          if (!cell.dataset.label && headers[index]) {
            cell.dataset.label = headers[index];
          }
          if (cell.dataset.label) {
            cell.setAttribute('aria-label', `${cell.dataset.label}: ${cell.textContent.trim()}`.trim());
          }
        });
      });
    });
  };

  syncResponsiveTableCards();
  window.addEventListener('resize', () => syncResponsiveTableCards(), { passive: true });
  window.visualViewport?.addEventListener('resize', () => syncResponsiveTableCards(), { passive: true });

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

  document.querySelectorAll('.material-select-row').forEach(row => {
    const checkbox = row.querySelector('input[type="checkbox"]');
    const syncState = () => row.classList.toggle('is-selected', Boolean(checkbox?.checked));
    row.addEventListener('click', event => {
      if (event.target.closest('textarea, select')) return;
      if (!checkbox) return;
      // Клик по любой части строки ставит/снимает галочку. Нативный клик по самому checkbox не дублируем.
      if (!event.target.closest('input[type="checkbox"]')) {
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
      }
      syncState();
    });
    row.addEventListener('dblclick', event => {
      if (event.target.closest('a, button, form, input, textarea, select, label')) return;
      const href = row.dataset.href;
      if (href) {
        window.location.href = href;
      }
    });
    if (checkbox) {
      checkbox.addEventListener('change', syncState);
      syncState();
    }
  });

  document.querySelectorAll('.js-material-writeoff-form').forEach(form => {
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

    form.querySelectorAll('.material-task-check').forEach(check => {
      check.addEventListener('change', () => {
        const selection = readSelection();
        if (check.checked) {
          selection.add(String(check.value));
        } else {
          selection.delete(String(check.value));
        }
        writeSelection(selection);
        syncSelectionUi();
      });
    });

    clearBtn?.addEventListener('click', () => {
      clearSelection();
      syncSelectionUi();
    });

    form.addEventListener('submit', () => {
      syncSelectionUi();
    });

    if (noPersistSelection) {
      window.addEventListener('pagehide', clearSelection, { once: true });
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') clearSelection();
      });
    }

    syncSelectionUi();
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

  document.querySelectorAll('.js-writeoff-material-select').forEach(select => {
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
    if (!trigger || trigger.dataset.excelNoticeShown === '1') return;
    trigger.dataset.excelNoticeShown = '1';
    showCrmNotice(excelNoticeText, 'info');
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

  bindStatisticsTopCard({
    selector: '.developer-stat-summary-card-duration',
    currentPageSelector: '.developer-statistics-page-overview',
    datasetKey: 'overviewUrl',
    requestTop: requestStatisticsOverviewTop,
  });

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
      event.preventDefault();
      setBusyState(link);
      try {
        const response = await window.fetch(link.href, {
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const blob = await response.blob();
        triggerBlobDownload(blob, getDownloadFilename(response));
        showExcelReadyNotice(link);
      } catch (error) {
        window.location.href = link.href;
      } finally {
        restoreBusyState(link);
      }
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
          <button class="btn btn-outline-secondary js-crm-confirm-cancel" type="button">Отмена</button>
          <button class="btn btn-danger js-crm-confirm-ok" type="button">Удалить</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    return modal;
  };

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const submitter = event.submitter;
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
        submitter.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Удаление...';
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
  document.querySelectorAll('.js-glass-save-form').forEach(bindGlassSaveForm);

  document.querySelectorAll('.js-glass-ordered-edit-toggle').forEach(button => {
    button.addEventListener('click', () => {
      const row = button.closest('.glass-order-row');
      const form = row?.querySelector('.js-glass-ordered-edit-form');
      const view = row?.querySelector('.js-glass-ordered-size-view');
      if (!form) return;
      view?.classList.add('d-none');
      form.classList.remove('d-none');
      form.hidden = false;
      const firstInput = form.querySelector('input, select, textarea');
      firstInput?.focus();
    });
  });

  document.querySelectorAll('.js-glass-ordered-edit-cancel').forEach(button => {
    button.addEventListener('click', () => {
      const form = button.closest('.js-glass-ordered-edit-form');
      const row = form?.closest('.glass-order-row');
      const view = row?.querySelector('.js-glass-ordered-size-view');
      form?.classList.add('d-none');
      if (form) form.hidden = true;
      view?.classList.remove('d-none');
    });
  });

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
  document.querySelectorAll('.js-glass-status-form').forEach(bindGlassStatusForm);

  const glassManualModalElement = document.getElementById('glassManualTaskModal');
  const glassManualOpen = document.querySelector('.js-glass-manual-open');
  const glassManualForm = document.querySelector('.js-glass-manual-form');
  const glassManualModal = glassManualModalElement && window.bootstrap ? new bootstrap.Modal(glassManualModalElement) : null;
  glassManualOpen?.addEventListener('click', () => glassManualModal?.show());
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
  const modal = modalElement && window.bootstrap ? bootstrap.Modal.getOrCreateInstance(modalElement) : null;
  let apartments = [];
  try {
    apartments = JSON.parse(source?.textContent || '[]');
  } catch (error) {
    apartments = [];
  }

  const fields = {
    number: form.querySelector('[data-avr-number]'),
    floor: form.querySelector('[data-avr-floor]'),
    floorField: form.querySelector('[data-avr-floor-field]'),
    owner: form.querySelector('[data-avr-owner]'),
    address: form.querySelector('[data-avr-address]'),
    inspectionDate: form.querySelector('[data-avr-inspection-date]'),
    premiseType: form.querySelector('[data-avr-premise-type]'),
    phrase: form.querySelector('[data-avr-phrase]')
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

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form[action*="/site-errors/"][action$="/close"]').forEach(form => {
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
});

document.addEventListener('DOMContentLoaded', () => {
  const pickers = document.querySelectorAll('.js-developer-stat-range-picker');
  if (!pickers.length) return;

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

  pickers.forEach(picker => {
    const openButton = picker.querySelector('.js-developer-stat-range-open');
    if (!openButton) return;
    openButton.addEventListener('click', event => {
      event.preventDefault();
      open(picker);
    });
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


document.addEventListener('DOMContentLoaded', () => {
  const toggles = document.querySelectorAll('.js-developer-ip-toggle');
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
  });

  const hashId = decodeURIComponent((window.location.hash || '').replace(/^#/, ''));
  if (hashId) {
    const hashedItem = document.getElementById(hashId);
    if (hashedItem?.classList.contains('developer-ip-item')) {
      collapseSiblings(hashedItem);
      setExpanded(hashedItem, true);
    }
  }
});
