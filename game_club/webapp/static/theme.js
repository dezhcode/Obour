/* پوستهٔ روشن و تیره — در <head> هر صفحه (پیش از اولین رسم، تا صفحه یک لحظه سفید نشود).
   انتخاب کاربر: خودکار (مثل تلگرام، بیرون از تلگرام مثل گوشی) / روشن / تیره؛ در localStorage می ماند.
   html[data-theme] را می گذارد؛ رنگ ها در gc.css. با هر تغییر رویداد gc-theme روی window می آید. */
(() => {
  const KEY = 'gclub_theme', root = document.documentElement;
  const mode = () => { try { const v = JSON.parse(localStorage.getItem(KEY)); return v === 'light' || v === 'dark' ? v : 'auto'; } catch (e) { return 'auto'; } };
  const tg = () => (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData ? Telegram.WebApp : null);
  const sys = () => { try { return matchMedia('(prefers-color-scheme: dark)').matches; } catch (e) { return false; } };
  const dark = () => { const m = mode(); if (m !== 'auto') return m === 'dark'; const w = tg(); return w && w.colorScheme ? w.colorScheme === 'dark' : sys(); };
  function apply() {
    const d = dark(), was = root.dataset.theme;
    root.dataset.theme = d ? 'dark' : 'light';
    if (was && was !== root.dataset.theme) dispatchEvent(new CustomEvent('gc-theme', { detail: root.dataset.theme }));
  }
  function set(m) { try { localStorage.setItem(KEY, JSON.stringify(m)); } catch (e) {} apply(); }
  apply();
  try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', apply); } catch (e) {}
  try { if (tg()) tg().onEvent('themeChanged', apply); } catch (e) {}
  window.GCTheme = { mode, set, apply, dark: () => root.dataset.theme === 'dark' };
})();
