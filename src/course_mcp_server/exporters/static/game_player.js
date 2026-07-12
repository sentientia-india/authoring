/* ============================================================
   LEVEL-4 GAME LAYER
   Appended after the base player. Wraps base renderers to add:
   HUD top bar, locked progression, full-screen slide player,
   streaks, timed challenges, branching character scenes,
   media blocks, confetti celebration, and a certificate.
   ============================================================ */
(function () {
  "use strict";

  var GP_DEFAULTS = {
    branching_scenarios: true,
    locked_progression: true,
    streaks: true,
    timed_challenges: false,
    timer_seconds: 20,
    celebration: true,
    certificate: true,
  };

  function gpOptions(course) {
    return Object.assign({}, GP_DEFAULTS, course.game_options || {});
  }

  function gpLessons(course) {
    return flattenLessons(course).map(function (lesson) {
      return {
        lesson: lesson,
        lessonId: lessonIdFor(lesson.moduleIndex, lesson.lessonIndex),
        moduleTitle: lesson.moduleTitle,
      };
    });
  }

  function gpStreak(state) {
    return {
      streak: Number(state.streak || 0),
      bestStreak: Number(state.bestStreak || 0),
    };
  }

  /* ---------------- HUD ---------------- */

  function gpEnsureHud() {
    var hud = document.getElementById("hud-topbar");
    if (!hud) return null;
    if (!hud.dataset.ready) {
      hud.dataset.ready = "true";
      hud.innerHTML =
        '<span class="hud-chip hud-level">Level <b data-hud="level">1</b></span>' +
        '<div class="hud-xpbar" title="Progress to next level"><i data-hud="xpbar"></i></div>' +
        '<span class="hud-chip" data-hud="xp">0 XP</span>' +
        '<span class="hud-chip hud-streak" data-hud="streak" hidden>&#128293; 0</span>';
      hud.hidden = false;
    }
    return hud;
  }

  function gpUpdateHud(course, state) {
    var hud = gpEnsureHud();
    if (!hud) return;
    var game = gameDefaults(state || {});
    var level = Math.max(1, Math.floor(game.xp / 100) + 1);
    var into = game.xp % 100;
    var levelEl = hud.querySelector('[data-hud="level"]');
    var xpEl = hud.querySelector('[data-hud="xp"]');
    var barEl = hud.querySelector('[data-hud="xpbar"]');
    var streakEl = hud.querySelector('[data-hud="streak"]');
    if (levelEl) levelEl.textContent = String(level);
    if (xpEl) xpEl.textContent = game.xp + " XP";
    if (barEl) barEl.style.width = into + "%";
    var s = gpStreak(state || {});
    if (streakEl) {
      var show = gpOptions(course).streaks && s.streak > 1;
      streakEl.hidden = !show;
      streakEl.innerHTML = "&#128293; " + s.streak + "&times;";
      if (show) {
        streakEl.classList.remove("is-hot");
        void streakEl.offsetWidth;
        streakEl.classList.add("is-hot");
      }
    }
  }

  /* ---------------- locked progression ---------------- */

  function gpApplyLocks(course, state) {
    if (!gpOptions(course).locked_progression) return;
    var completed = state.completedLessons || [];
    var unlockedUpTo = 0;
    var all = gpLessons(course);
    for (var i = 0; i < all.length; i += 1) {
      unlockedUpTo = i;
      if (completed.indexOf(all[i].lessonId) < 0) break;
    }
    all.forEach(function (entry, index) {
      if (index <= unlockedUpTo) return;
      var card = document.querySelector('[data-lesson-id="' + entry.lessonId + '"]');
      if (!card || card.classList.contains("locked")) return;
      card.classList.add("locked");
      var meta = card.querySelector(".lesson-meta");
      if (meta && !meta.querySelector(".lock-chip")) {
        var chip = document.createElement("span");
        chip.className = "lock-chip";
        chip.innerHTML = "&#128274; Finish previous lesson";
        meta.appendChild(chip);
      }
      card.querySelectorAll(".lesson-actions button").forEach(function (button) {
        button.disabled = true;
      });
    });
  }

  /* ---------------- media rendering ---------------- */

  function gpMediaHtml(media) {
    if (!media || !media.src) return "";
    var caption = media.caption
      ? "<figcaption>" + escapeHtml(media.caption) + "</figcaption>"
      : "";
    if (media.kind === "image") {
      return (
        '<figure class="block-media"><img src="' +
        escapeHtml(media.src) +
        '" alt="' +
        escapeHtml(media.alt || "") +
        '" loading="lazy">' +
        caption +
        "</figure>"
      );
    }
    if (media.kind === "video") {
      var src = String(media.src);
      var isFile = /\.(mp4|webm)(\?|$)/i.test(src) || src.indexOf("assets/media/") === 0;
      var allowedEmbed = /^https:\/\/(www\.youtube(-nocookie)?\.com|youtube\.com|player\.vimeo\.com|www\.loom\.com)\//i.test(src);
      if (!isFile && !allowedEmbed) {
        return (
          '<div class="video-poster"><span class="video-poster-icon">&#9658;</span>' +
          '<div><b>Video slot</b><p>' + escapeHtml(media.caption || "A video will appear here.") + "</p></div></div>"
        );
      }
      var inner = isFile
        ? '<video src="' + escapeHtml(src) + '" controls preload="metadata"></video>'
        : '<iframe src="' + escapeHtml(src) + '" title="Lesson video" allowfullscreen loading="lazy"></iframe>';
      return '<figure class="block-media"><div class="video-frame">' + inner + "</div>" + caption + "</figure>";
    }
    if (media.kind === "video_slot") {
      return (
        '<div class="video-poster"><span class="video-poster-icon">&#9658;</span>' +
        '<div><b>' + escapeHtml(media.caption || "Video coming soon") + "</b>" +
        "<p>" + escapeHtml(media.alt || "This spot is reserved for a short video.") + "</p></div></div>"
      );
    }
    return (
      '<a class="media-link-card" href="' +
      escapeHtml(media.src) +
      '" target="_blank" rel="noopener"><span>' +
      escapeHtml(media.caption || media.alt || media.src) +
      "</span></a>"
    );
  }

  /* ---------------- confetti ---------------- */

  function gpConfetti(count) {
    var canvas = document.getElementById("fx-canvas");
    if (!canvas) return;
    var ctx = canvas.getContext("2d");
    canvas.hidden = false;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    var colors = ["#2dd4bf", "#38bdf8", "#fb923c", "#a78bfa", "#4ade80", "#f472b6", "#fbbf24"];
    var parts = [];
    for (var i = 0; i < (count || 120); i += 1) {
      parts.push({
        x: canvas.width / 2 + (Math.random() - 0.5) * canvas.width * 0.5,
        y: canvas.height * 0.32,
        vx: (Math.random() - 0.5) * 13,
        vy: -(Math.random() * 11 + 5),
        size: Math.random() * 8 + 4,
        color: colors[Math.floor(Math.random() * colors.length)],
        rot: Math.random() * Math.PI,
        vr: (Math.random() - 0.5) * 0.3,
      });
    }
    var start = performance.now();
    function tick(now) {
      var elapsed = now - start;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      parts.forEach(function (p) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.34;
        p.rot += p.vr;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = Math.max(0, 1 - elapsed / 2100);
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.62);
        ctx.restore();
      });
      if (elapsed < 2200) {
        requestAnimationFrame(tick);
      } else {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        canvas.hidden = true;
      }
    }
    requestAnimationFrame(tick);
  }

  /* ---------------- branching character scene ---------------- */

  function gpBranchScene(activity, course, index, state) {
    var card = document.createElement("article");
    var activityId = activity.activity_id || "branching-" + index;
    var doneAlready = gameDefaults(state).completedActivities.indexOf(activityId) >= 0;
    card.className = "activity-card " + (doneAlready ? "completed" : "");
    var persona = activity.persona || {};
    var name = persona.name || "Alex";
    var role = persona.role || "Scenario partner";
    var nodes = (activity.items || []).filter(function (item) {
      return item && (item.choices || item.options);
    });
    card.innerHTML =
      '<div class="activity-type">Branching scenario</div>' +
      '<span class="activity-status">' + (doneAlready ? "Completed" : "+45 XP") + "</span>" +
      "<h3>" + escapeHtml(activity.title || "Scenario") + "</h3>" +
      "<p>" + escapeHtml(activity.objective || activity.instructions || "Choose how the conversation unfolds.") + "</p>" +
      '<div class="branch-scene">' +
      '<div class="branch-persona">' +
      '<div class="branch-avatar">' + escapeHtml(name.charAt(0).toUpperCase()) + "</div>" +
      '<div><div class="branch-name">' + escapeHtml(name) + '</div><div class="branch-role">' + escapeHtml(role) + "</div></div>" +
      "</div>" +
      '<p class="branch-progress"></p>' +
      '<div class="branch-bubble"></div>' +
      '<div class="scenario-options"></div>' +
      '<div class="activity-feedback" role="status"></div>' +
      "</div>";
    var bubble = card.querySelector(".branch-bubble");
    var optionsBox = card.querySelector(".scenario-options");
    var feedback = card.querySelector(".activity-feedback");
    var progress = card.querySelector(".branch-progress");
    var nodeIndex = 0;
    var best = 0;

    function playNode() {
      if (nodeIndex >= nodes.length) {
        var pct = nodes.length ? Math.round((best / nodes.length) * 100) : 100;
        bubble.textContent = "That closes the scenario. You chose the strongest response " + pct + "% of the time.";
        optionsBox.innerHTML = "";
        progress.textContent = "Scenario complete";
        card.classList.add("completed");
        var status = card.querySelector(".activity-status");
        if (status) status.textContent = "Completed";
        markActivityComplete(course, loadState(course), activityId, 45);
        if (CourseScorm.recordInteraction) {
          CourseScorm.recordInteraction("branching-" + index, "choice", "score:" + pct, pct >= 60 ? "correct" : "neutral", activity.title || "Branching scenario");
        }
        return;
      }
      var node = nodes[nodeIndex];
      progress.textContent = "Scene " + (nodeIndex + 1) + " of " + nodes.length;
      bubble.textContent = node.scenario || node.prompt || "What do you do next?";
      var choices = node.choices || node.options || [];
      optionsBox.innerHTML = "";
      choices.forEach(function (choice, choiceIndex) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "sp-option";
        button.textContent = choice.label || choice.text || "Option " + (choiceIndex + 1);
        button.addEventListener("click", function () {
          var isBest = (choice.result || "") === "best";
          if (isBest) best += 1;
          feedback.textContent = choice.feedback || choice.consequence || (isBest ? "Strong choice." : "There is a stronger option - notice what it protects.");
          optionsBox.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
          button.classList.add(isBest ? "is-correct" : "is-wrong");
          setTimeout(function () {
            nodeIndex += 1;
            feedback.textContent = "";
            playNode();
          }, 1400);
        });
        optionsBox.appendChild(button);
      });
    }
    playNode();
    return card;
  }

  /* ---------------- slide player ---------------- */

  var gpPlayerCtx = null;

  function gpBuildSlides(course, entry) {
    var lesson = entry.lesson;
    var slides = [{ kind: "title" }];
    (lesson.content_blocks || []).forEach(function (block) {
      if (block && (block.text || block.media)) slides.push({ kind: "block", block: block });
    });
    (lesson.activities || []).forEach(function (activity, i) {
      slides.push({ kind: "activity", activity: activity, index: i });
    });
    (lesson.quiz_questions || []).forEach(function (question) {
      slides.push({ kind: "question", question: question });
    });
    slides.push({ kind: "finale" });
    return slides;
  }

  function gpClosePlayer() {
    if (!gpPlayerCtx) return;
    if (gpPlayerCtx.timer) clearInterval(gpPlayerCtx.timer);
    document.removeEventListener("keydown", gpPlayerCtx.onKey);
    gpPlayerCtx.overlay.hidden = true;
    gpPlayerCtx = null;
  }

  function gpOpenPlayer(course, lessonId) {
    var overlay = document.getElementById("slide-player");
    if (!overlay) {
      openLesson(course, loadState(course), lessonId);
      return;
    }
    var found = findLessonById(course, lessonId);
    if (!found) return;
    var entry = { lesson: found.lesson, lessonId: lessonId, moduleTitle: found.module.title || "Module " + (found.moduleIndex + 1) };
    var slides = gpBuildSlides(course, entry);
    var startXp = gameDefaults(loadState(course)).xp;
    gpPlayerCtx = {
      course: course,
      entry: entry,
      slides: slides,
      index: 0,
      overlay: overlay,
      startXp: startXp,
      timer: null,
      observer: null,
      onKey: function (event) {
        if (event.key === "Escape") gpClosePlayer();
        if (event.key === "ArrowRight") {
          var btn = overlay.querySelector(".sp-continue");
          if (btn && !btn.disabled) btn.click();
        }
        if (event.key === "ArrowLeft") {
          var back = overlay.querySelector('[data-sp="back"]');
          if (back && !back.disabled) back.click();
        }
      },
    };
    overlay.hidden = false;
    document.addEventListener("keydown", gpPlayerCtx.onKey);
    CourseScorm.setLocation(lessonId);
    gpRenderSlide();
  }

  function gpSegmentsHtml(ctx) {
    var out = "";
    for (var i = 0; i < ctx.slides.length; i += 1) {
      out += '<i class="' + (i < ctx.index ? "done" : i === ctx.index ? "now" : "") + '"></i>';
    }
    return out;
  }

  function gpSlideShellHtml(ctx) {
    return (
      '<div class="sp-top">' +
      '<span class="sp-lesson-label">' + escapeHtml(ctx.entry.moduleTitle) + "</span>" +
      '<div class="sp-segments">' + gpSegmentsHtml(ctx) + "</div>" +
      '<button class="sp-close" type="button" aria-label="Close lesson" data-sp="close">&#10005;</button>' +
      "</div>" +
      '<div class="sp-stage-wrap"><div class="sp-stage"></div></div>' +
      '<div class="sp-bottom">' +
      '<span class="sp-hint">Use &#8592; &#8594; keys &middot; Esc to exit</span>' +
      '<div class="sp-nav">' +
      '<button class="secondary" type="button" data-sp="back">Back</button>' +
      '<button class="primary sp-continue" type="button" data-sp="next">Continue</button>' +
      "</div></div>"
    );
  }

  function gpSetContinueEnabled(enabled) {
    if (!gpPlayerCtx) return;
    var btn = gpPlayerCtx.overlay.querySelector(".sp-continue");
    if (btn) btn.disabled = !enabled;
  }

  function gpGateOnCompletion(card) {
    gpSetContinueEnabled(card.classList.contains("completed"));
    if (gpPlayerCtx.observer) gpPlayerCtx.observer.disconnect();
    gpPlayerCtx.observer = new MutationObserver(function () {
      if (card.classList.contains("completed")) gpSetContinueEnabled(true);
    });
    gpPlayerCtx.observer.observe(card, { attributes: true, attributeFilter: ["class"] });
  }

  function gpRenderQuestion(stage, question) {
    var ctx = gpPlayerCtx;
    var options = gpOptions(ctx.course);
    stage.innerHTML =
      '<p class="sp-kicker">Knowledge check</p>' +
      "<h2>" + escapeHtml(question.question || "Choose the best answer.") + "</h2>" +
      '<div class="sp-question-options"></div>';
    if (options.timed_challenges) {
      var timerEl = document.createElement("div");
      timerEl.className = "sp-timer";
      timerEl.innerHTML = "<b>" + options.timer_seconds + "</b>";
      stage.querySelector("h2").before(timerEl);
      var remaining = options.timer_seconds;
      ctx.timer = setInterval(function () {
        remaining -= 1;
        timerEl.style.setProperty("--t", Math.max(0, (remaining / options.timer_seconds) * 100) + "%");
        timerEl.querySelector("b").textContent = String(Math.max(0, remaining));
        if (remaining <= 5) timerEl.classList.add("is-critical");
        if (remaining <= 0) {
          clearInterval(ctx.timer);
          ctx.timer = null;
          settle(null);
        }
      }, 1000);
    }
    var box = stage.querySelector(".sp-question-options");
    var correct = question.correct_answers || [];
    var settled = false;

    function settle(chosenButton) {
      if (settled) return;
      settled = true;
      if (ctx.timer) {
        clearInterval(ctx.timer);
        ctx.timer = null;
      }
      var isCorrect = Boolean(chosenButton) && correct.indexOf(chosenButton.textContent) >= 0;
      box.querySelectorAll("button").forEach(function (b) {
        b.disabled = true;
        if (correct.indexOf(b.textContent) >= 0) b.classList.add("is-correct");
      });
      if (chosenButton && !isCorrect) chosenButton.classList.add("is-wrong");
      var state = loadState(ctx.course);
      var s = gpStreak(state);
      var earned = 0;
      if (isCorrect) {
        s.streak += 1;
        s.bestStreak = Math.max(s.bestStreak, s.streak);
        earned = 20 + (options.streaks ? Math.min(s.streak - 1, 5) * 5 : 0);
      } else {
        s.streak = 0;
      }
      var merged = Object.assign({}, state, s);
      saveState(ctx.course, merged);
      if (earned) {
        awardProgress(ctx.course, merged, "question", earned);
        var pop = document.createElement("span");
        pop.className = "sp-xp-pop";
        pop.textContent = "+" + earned + " XP" + (s.streak > 1 ? " 🔥" + s.streak + "×" : "");
        stage.style.position = "relative";
        stage.appendChild(pop);
      } else {
        gpUpdateHud(ctx.course, merged);
      }
      var explain = document.createElement("div");
      explain.className = "sp-explain" + (isCorrect ? "" : " is-wrong");
      explain.textContent = (isCorrect ? "Correct. " : chosenButton ? "Not quite. " : "Time's up. ") + (question.explanation || "");
      stage.appendChild(explain);
      if (CourseScorm.recordInteraction) {
        CourseScorm.recordInteraction(question.id || "question", "choice", chosenButton ? chosenButton.textContent : "timeout", isCorrect ? "correct" : "wrong", question.question || "Question");
      }
      gpSetContinueEnabled(true);
    }

    (question.options || []).forEach(function (option) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "sp-option";
      button.textContent = option;
      button.addEventListener("click", function () { settle(button); });
      box.appendChild(button);
    });
    gpSetContinueEnabled(false);
  }

  function gpRenderSlide(direction) {
    var ctx = gpPlayerCtx;
    if (!ctx) return;
    if (ctx.timer) {
      clearInterval(ctx.timer);
      ctx.timer = null;
    }
    if (ctx.observer) {
      ctx.observer.disconnect();
      ctx.observer = null;
    }
    ctx.overlay.innerHTML = gpSlideShellHtml(ctx);
    var stage = ctx.overlay.querySelector(".sp-stage");
    var slide = ctx.slides[ctx.index];
    var lesson = ctx.entry.lesson;
    gpSetContinueEnabled(true);

    if (slide.kind === "title") {
      stage.innerHTML =
        '<p class="sp-kicker">' + escapeHtml(ctx.entry.moduleTitle) + "</p>" +
        "<h1>" + escapeHtml(lesson.title || "Lesson") + "</h1>" +
        '<div class="sp-body"><p>' + escapeHtml(lesson.objective || "") + "</p></div>" +
        '<div class="sp-meta-row">' +
        '<span class="hud-chip">' + (lesson.duration_minutes || 8) + " min</span>" +
        '<span class="hud-chip">' + (lesson.content_blocks || []).length + " ideas</span>" +
        '<span class="hud-chip">' + ((lesson.activities || []).length + (lesson.quiz_questions || []).length) + " interactions</span>" +
        "</div>";
    } else if (slide.kind === "block") {
      var block = slide.block;
      var parts = segmentText(block.text || "", 900);
      stage.dataset.cbId = block.id || "";
      stage.innerHTML =
        '<p class="sp-kicker">' + escapeHtml(blockTitle(block.type)) + "</p>" +
        '<div class="sp-body">' +
        parts.map(function (part) { return "<p>" + escapeHtml(part) + "</p>"; }).join("") +
        gpMediaHtml(block.media) +
        "</div>";
    } else if (slide.kind === "activity") {
      stage.innerHTML = '<p class="sp-kicker">Interactive practice</p>';
      var card = renderNativeActivity(slide.activity, ctx.course, slide.index, loadState(ctx.course));
      stage.appendChild(card);
      gpGateOnCompletion(card);
    } else if (slide.kind === "question") {
      gpRenderQuestion(stage, slide.question);
    } else if (slide.kind === "finale") {
      var state = loadState(ctx.course);
      var sessionXp = Math.max(0, gameDefaults(state).xp - ctx.startXp);
      var s = gpStreak(state);
      var opts = gpOptions(ctx.course);
      var next = nextLessonId(ctx.course, ctx.entry.lessonId);
      stage.innerHTML =
        '<div class="sp-finale">' +
        '<p class="sp-kicker">Lesson complete</p>' +
        '<div class="sp-finale-score">+' + sessionXp + " XP</div>" +
        "<h2>" + escapeHtml(lesson.title || "Lesson") + "</h2>" +
        '<div class="sp-finale-stats">' +
        '<span class="hud-chip">Best streak &#128293; ' + s.bestStreak + "</span>" +
        '<span class="hud-chip">Total ' + gameDefaults(state).xp + " XP</span>" +
        "</div>" +
        '<div class="sp-finale-actions">' +
        '<button class="complete" type="button" data-sp="finish">Complete lesson</button>' +
        (next ? '<button class="primary" type="button" data-sp="next-lesson">Next lesson &#8594;</button>' : "") +
        "</div></div>";
      if (opts.celebration) gpConfetti(130);
      var finish = stage.querySelector('[data-sp="finish"]');
      if (finish) {
        finish.addEventListener("click", function () {
          markLessonDone(ctx.course, loadState(ctx.course), ctx.entry.lessonId);
          gpClosePlayer();
        });
      }
      var nextBtn = stage.querySelector('[data-sp="next-lesson"]');
      if (nextBtn) {
        nextBtn.addEventListener("click", function () {
          markLessonDone(ctx.course, loadState(ctx.course), ctx.entry.lessonId);
          var course = ctx.course;
          gpClosePlayer();
          gpOpenPlayer(course, next);
        });
      }
      var continueBtn = ctx.overlay.querySelector(".sp-continue");
      if (continueBtn) continueBtn.hidden = true;
    }

    var closeBtn = ctx.overlay.querySelector('[data-sp="close"]');
    if (closeBtn) closeBtn.addEventListener("click", gpClosePlayer);
    var backBtn = ctx.overlay.querySelector('[data-sp="back"]');
    if (backBtn) {
      backBtn.disabled = ctx.index === 0;
      backBtn.addEventListener("click", function () {
        if (ctx.index > 0) {
          ctx.index -= 1;
          gpRenderSlide("back");
        }
      });
    }
    var nextNav = ctx.overlay.querySelector('[data-sp="next"]');
    if (nextNav) {
      nextNav.addEventListener("click", function () {
        if (ctx.index < ctx.slides.length - 1) {
          var stageEl = ctx.overlay.querySelector(".sp-stage");
          stageEl.classList.add("slide-out");
          setTimeout(function () {
            ctx.index += 1;
            gpRenderSlide("next");
          }, 180);
        }
      });
    }
  }

  /* ---------------- certificate ---------------- */

  function gpShowCertificate(course, state) {
    var root = document.getElementById("certificate-root");
    if (!root) return;
    var game = gameDefaults(state);
    var today = new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
    root.innerHTML =
      '<div class="certificate-sheet" role="dialog" aria-label="Certificate of completion">' +
      '<span class="cert-kicker">Certificate of Completion</span>' +
      '<h1 class="cert-title">' + escapeHtml(course.course_title || "Course") + "</h1>" +
      '<div class="cert-body">This certifies that</div>' +
      '<div class="cert-name" contenteditable="true" spellcheck="false">Your Name</div>' +
      '<div class="cert-body">has successfully completed the course with a final score of</div>' +
      '<div class="cert-score">' + (game.quizScore || 0) + "%</div>" +
      '<div class="cert-footer">' +
      "<span><b>" + today + "</b>Date</span>" +
      "<span><b>" + game.xp + " XP</b>Experience earned</span>" +
      "</div>" +
      '<div class="cert-seal">&#127942;</div>' +
      '<div class="cert-actions">' +
      '<button class="primary" type="button" data-cert="print">Print / Save PDF</button>' +
      '<button class="secondary" type="button" data-cert="close">Close</button>' +
      "</div></div>";
    root.hidden = false;
    root.querySelector('[data-cert="print"]').addEventListener("click", function () { window.print(); });
    root.querySelector('[data-cert="close"]').addEventListener("click", function () { root.hidden = true; });
  }

  /* ---------------- wire into the base player ---------------- */

  var baseRenderGameCard = renderGameCard;
  renderGameCard = function (course, state) {
    baseRenderGameCard(course, state);
    gpUpdateHud(course, state);
  };

  var baseRenderNativeActivity = renderNativeActivity;
  renderNativeActivity = function (activity, course, index, state) {
    var type = String(activity.activity_type || activity.type || "").toLowerCase();
    if (type.indexOf("branching") >= 0 && gpOptions(course).branching_scenarios) {
      return gpBranchScene(activity, course, index, state);
    }
    return baseRenderNativeActivity(activity, course, index, state);
  };

  var baseRenderTextBlock = renderTextBlock;
  renderTextBlock = function (block, label) {
    var html = baseRenderTextBlock(block, label);
    if (block && block.media) {
      html = html.replace(/<\/section>\s*$/, gpMediaHtml(block.media) + "</section>");
    }
    return html;
  };

  var baseMarkLessonDone = markLessonDone;
  markLessonDone = function (course, state, lessonId) {
    var isNew = (state.completedLessons || []).indexOf(lessonId) < 0;
    baseMarkLessonDone(course, state, lessonId);
    if (isNew && gpOptions(course).celebration && !gpPlayerCtx) gpConfetti(90);
  };

  var baseRenderCompletionScreen = renderCompletionScreen;
  renderCompletionScreen = function (course, state) {
    baseRenderCompletionScreen(course, state);
    if (!gpOptions(course).certificate) return;
    var screen = document.querySelector(".completion-screen");
    if (screen && !screen.querySelector("[data-cert-open]")) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "primary";
      button.dataset.certOpen = "true";
      button.textContent = "View certificate";
      button.addEventListener("click", function () { gpShowCertificate(course, loadState(course)); });
      screen.appendChild(button);
    }
    if (gpOptions(course).celebration) gpConfetti(160);
  };

  var baseRenderCoursePlayer = renderCoursePlayer;
  renderCoursePlayer = function (course, providedState) {
    baseRenderCoursePlayer(course, providedState);
    var state = providedState || loadState(course);
    gpEnsureHud();
    gpUpdateHud(course, state);
    gpApplyLocks(course, state);
    var deck = document.getElementById("lesson-deck");
    if (deck && !deck.dataset.gpBound) {
      deck.dataset.gpBound = "true";
      deck.addEventListener(
        "click",
        function (event) {
          var button = event.target.closest('[data-action="open"]');
          if (!button) return;
          var card = button.closest("[data-lesson-id]");
          if (!card || card.classList.contains("locked")) return;
          if (!document.getElementById("slide-player")) return;
          event.stopImmediatePropagation();
          event.preventDefault();
          gpOpenPlayer(course, card.dataset.lessonId);
        },
        true
      );
    }
  };

  /* re-render once so the game layer applies to the initial paint */
  var gpCourse = typeof getEmbeddedCourseData === "function" ? getEmbeddedCourseData() : null;
  if (gpCourse && document.body.dataset.coursePlayer !== undefined) {
    renderCoursePlayer(gpCourse, loadState(gpCourse));
  }
})();
