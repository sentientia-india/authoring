(function () {
  function safeParseProject(shell) {
    try { return JSON.parse(shell.getAttribute('data-video-project') || '{}'); }
    catch (e) { console.error('Invalid video project JSON', e); return { scenes: [] }; }
  }

  function emitLearningEvent(type, detail) {
    const event = { type, detail, ts: new Date().toISOString() };
    window.dispatchEvent(new CustomEvent('sentientia:learning-event', { detail: event }));
    if (window.SentientiaSCORM && typeof window.SentientiaSCORM.trackEvent === 'function') {
      window.SentientiaSCORM.trackEvent(type, detail);
    }
    if (window.SentientiaGame && typeof window.SentientiaGame.applyEvent === 'function') {
      window.SentientiaGame.applyEvent(type, detail);
    }
    console.debug('[learning-event]', event);
  }

  class SceneVideoPlayer {
    constructor(shell) {
      this.shell = shell;
      this.project = safeParseProject(shell);
      this.stage = document.getElementById('sv-stage');
      this.caption = document.getElementById('sv-caption');
      this.progress = document.getElementById('sv-progress');
      this.playBtn = document.getElementById('sv-play');
      this.pauseBtn = document.getElementById('sv-pause');
      this.prevBtn = document.getElementById('sv-prev');
      this.nextBtn = document.getElementById('sv-next');
      this.sceneIndex = 0;
      this.elapsedInScene = 0;
      this.timer = null;
      this.pausedForInteraction = false;
      this.bind();
      this.renderScene();
    }

    bind() {
      this.playBtn.addEventListener('click', () => this.play());
      this.pauseBtn.addEventListener('click', () => this.pause());
      this.prevBtn.addEventListener('click', () => this.go(-1));
      this.nextBtn.addEventListener('click', () => this.go(1));
      window.addEventListener('keydown', (ev) => {
        if (ev.key === ' ') { ev.preventDefault(); this.timer ? this.pause() : this.play(); }
        if (ev.key === 'ArrowRight') this.go(1);
        if (ev.key === 'ArrowLeft') this.go(-1);
      });
    }

    currentScene() { return (this.project.scenes || [])[this.sceneIndex]; }

    play() {
      if (!this.currentScene()) return;
      this.pausedForInteraction = false;
      if (this.timer) return;
      emitLearningEvent('video_scene_started', { sceneId: this.currentScene().id, title: this.currentScene().title });
      this.timer = setInterval(() => this.tick(), 1000);
    }

    pause() {
      clearInterval(this.timer);
      this.timer = null;
    }

    go(delta) {
      this.pause();
      this.sceneIndex = Math.max(0, Math.min((this.project.scenes || []).length - 1, this.sceneIndex + delta));
      this.elapsedInScene = 0;
      this.pausedForInteraction = false;
      this.renderScene();
    }

    tick() {
      const scene = this.currentScene();
      if (!scene) return this.pause();
      this.elapsedInScene += 1;
      this.updateCaption();
      this.updateProgress();
      const shouldPause = scene.interactions && scene.interactions.length && this.elapsedInScene >= Math.floor(scene.duration_seconds * 0.55);
      if (shouldPause && !this.pausedForInteraction) {
        this.pausedForInteraction = true;
        this.pause();
        this.renderInteraction(scene.interactions[0]);
        return;
      }
      if (this.elapsedInScene >= scene.duration_seconds) {
        emitLearningEvent('video_scene_completed', { sceneId: scene.id });
        if (this.sceneIndex < (this.project.scenes || []).length - 1) {
          this.sceneIndex += 1;
          this.elapsedInScene = 0;
          this.renderScene();
        } else {
          this.pause();
          emitLearningEvent('interactive_video_completed', { videoId: this.project.video_id });
        }
      }
    }

    updateProgress() {
      const scenes = this.project.scenes || [];
      const before = scenes.slice(0, this.sceneIndex).reduce((n, s) => n + (s.duration_seconds || 0), 0);
      const total = scenes.reduce((n, s) => n + (s.duration_seconds || 0), 0) || 1;
      this.progress.value = Math.min(100, ((before + this.elapsedInScene) / total) * 100);
    }

    updateCaption() {
      const scene = this.currentScene();
      const cue = (scene.captions || []).find(c => this.elapsedInScene >= c.start && this.elapsedInScene <= c.end);
      this.caption.textContent = cue ? cue.text : '';
    }

    renderScene() {
      const scene = this.currentScene();
      if (!scene) return;
      this.stage.innerHTML = '';
      const card = document.createElement('article');
      card.className = 'sv-scene sv-scene-' + scene.type;
      card.innerHTML = `
        <div class="sv-scene-meta">Scene ${this.sceneIndex + 1} / ${(this.project.scenes || []).length}</div>
        <h1>${escapeHtml(scene.title)}</h1>
        <div class="sv-visual" aria-hidden="true">
          <div class="sv-orb"></div>
          <div class="sv-path"></div>
          <p>${escapeHtml(scene.visual_prompt || '')}</p>
        </div>
        <ul class="sv-onscreen">${(scene.on_screen_text || []).map(t => `<li>${escapeHtml(t)}</li>`).join('')}</ul>
      `;
      this.stage.appendChild(card);
      this.caption.textContent = '';
      this.updateProgress();
    }

    renderInteraction(interaction) {
      const panel = document.createElement('section');
      panel.className = 'sv-interaction';
      const choices = interaction.choices || [];
      panel.innerHTML = `<h2>${escapeHtml(interaction.prompt || 'Choose the best answer')}</h2>`;
      choices.forEach((choice, index) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = choice;
        btn.addEventListener('click', () => {
          const correct = index === interaction.correct_index;
          btn.classList.add(correct ? 'is-correct' : 'is-wrong');
          emitLearningEvent('video_checkpoint_completed', {
            sceneId: this.currentScene().id,
            prompt: interaction.prompt,
            selectedIndex: index,
            correct,
            score: correct ? 100 : 0
          });
          setTimeout(() => {
            panel.remove();
            this.play();
          }, 900);
        });
        panel.appendChild(btn);
      });
      this.stage.appendChild(panel);
      emitLearningEvent('video_checkpoint_presented', { sceneId: this.currentScene().id });
    }
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[c];
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    const shell = document.querySelector('.sv-shell');
    if (shell) window.SentientiaSceneVideo = new SceneVideoPlayer(shell);
  });
})();
