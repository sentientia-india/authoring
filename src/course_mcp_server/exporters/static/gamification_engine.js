(function () {
  const defaultState = { xp: 0, level: 1, completed: {}, achievements: [] };
  const config = { xpLesson: 50, xpActivity: 75, xpCorrect: 20, xpWrong: 2, levelCurve: [0,100,250,500,900,1400,2100] };
  function levelFor(xp) { let level = 1; config.levelCurve.forEach((t, i) => { if (xp >= t) level = i + 1; }); return level; }
  function load() { try { return JSON.parse(localStorage.getItem('sentientiaGame') || 'null') || defaultState; } catch { return defaultState; } }
  function save(state) { localStorage.setItem('sentientiaGame', JSON.stringify(state)); render(state); }
  function award(state, id, title) { if (!state.achievements.find(a => a.id === id)) state.achievements.push({ id, title, at: new Date().toISOString() }); }
  function applyEvent(type, detail) {
    const state = load();
    const key = type + ':' + (detail.sceneId || detail.lessonId || detail.activityId || detail.objectId || Date.now());
    if (state.completed[key]) return state;
    state.completed[key] = true;
    if (type.includes('lesson') && type.includes('completed')) state.xp += config.xpLesson;
    else if (type.includes('activity') && type.includes('completed')) state.xp += config.xpActivity;
    else if (type.includes('checkpoint')) state.xp += detail.correct ? config.xpCorrect : config.xpWrong;
    else if (type.includes('video') && type.includes('completed')) state.xp += config.xpActivity;
    state.level = levelFor(state.xp);
    if (state.xp >= 250) award(state, 'badge_momentum', 'Momentum Builder');
    if (state.level >= 5) award(state, 'badge_level_5', 'Level 5 Achiever');
    save(state);
    return state;
  }
  function render(state) {
    let hud = document.getElementById('sentientia-game-hud');
    if (!hud) {
      hud = document.createElement('aside');
      hud.id = 'sentientia-game-hud';
      hud.style.cssText = 'position:fixed;right:16px;top:16px;z-index:9999;background:#fff;color:#111;padding:10px 14px;border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.2);font:600 14px system-ui';
      document.body.appendChild(hud);
    }
    hud.innerHTML = `XP ${state.xp} · Level ${state.level} · Badges ${state.achievements.length}`;
  }
  window.SentientiaGame = { applyEvent, load, save };
  document.addEventListener('DOMContentLoaded', () => render(load()));
})();
