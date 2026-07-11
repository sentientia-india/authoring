(function () {
  "use strict";

  var debug = false;
  var initialized = false;
  var startTime = new Date();
  var apiHandle = null;
  var apiVersion = null;

  function log(message) {
    if (debug && window.console) console.log("[CourseScorm] " + message);
  }

  function findApi(win, apiName) {
    var attempts = 0;
    while (win && attempts < 10) {
      if (win[apiName]) return win[apiName];
      if (win.parent && win.parent !== win) win = win.parent;
      else break;
      attempts += 1;
    }
    return null;
  }

  function findApiInFrames(win, apiName, visited) {
    if (!win) return null;
    visited = visited || [];
    if (visited.indexOf(win) !== -1) return null;
    visited.push(win);

    var direct = findApi(win, apiName);
    if (direct) return direct;

    // SCORM Cloud's modern player can host the API in a sibling player frame
    // when content is opened in a popup. Search same-origin child frames as a
    // fallback after checking the normal parent/opener chain.
    try {
      for (var index = 0; index < win.frames.length; index += 1) {
        var nested = findApiInFrames(win.frames[index], apiName, visited);
        if (nested) return nested;
      }
    } catch (_error) {
      // A cross-origin frame is not a valid SCORM API host for this package.
    }
    return null;
  }

  function discoverApi() {
    if (apiHandle) return apiHandle;
    apiHandle = findApiInFrames(window, "API");
    if (apiHandle) {
      apiVersion = "1.2";
      return apiHandle;
    }
    apiHandle = findApiInFrames(window, "API_1484_11");
    if (apiHandle) {
      apiVersion = "2004";
      return apiHandle;
    }
    if (window.opener && !window.opener.closed) {
      apiHandle = findApiInFrames(window.opener, "API") || findApiInFrames(window.opener, "API_1484_11");
      apiVersion = apiHandle && apiHandle.LMSInitialize ? "1.2" : apiHandle ? "2004" : null;
    }
    return apiHandle;
  }

  function call(method12, method2004, arg) {
    var api = discoverApi();
    if (!api) return false;
    try {
      if (apiVersion === "1.2" && typeof api[method12] === "function") {
        return api[method12](arg == null ? "" : arg);
      }
      if (apiVersion === "2004" && typeof api[method2004] === "function") {
        return api[method2004](arg == null ? "" : arg);
      }
    } catch (e) {
      log("SCORM call failed: " + e.message);
    }
    return false;
  }

  function setValue(key12, key2004, value) {
    var api = discoverApi();
    if (!api) return false;
    try {
      if (apiVersion === "1.2" && typeof api.LMSSetValue === "function") return api.LMSSetValue(key12, String(value));
      if (apiVersion === "2004" && typeof api.SetValue === "function") return api.SetValue(key2004, String(value));
    } catch (e) {
      log("SCORM set failed: " + e.message);
    }
    return false;
  }

  function getValue(key12, key2004) {
    var api = discoverApi();
    if (!api) return "";
    try {
      if (apiVersion === "1.2" && typeof api.LMSGetValue === "function") return api.LMSGetValue(key12);
      if (apiVersion === "2004" && typeof api.GetValue === "function") return api.GetValue(key2004);
    } catch (e) {
      log("SCORM get failed: " + e.message);
    }
    return "";
  }

  function toScorm12Time(ms) {
    var total = Math.floor(ms / 1000);
    var h = String(Math.floor(total / 3600)).padStart(4, "0");
    var m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
    var s = String(total % 60).padStart(2, "0");
    return h + ":" + m + ":" + s;
  }

  function toScorm2004Time(ms) {
    var total = Math.floor(ms / 1000);
    var h = Math.floor(total / 3600);
    var m = Math.floor((total % 3600) / 60);
    var s = total % 60;
    return "PT" + h + "H" + m + "M" + s + "S";
  }

  window.CourseScorm = {
    enableDebug: function () { debug = true; },
    api: discoverApi,
    version: function () { discoverApi(); return apiVersion; },
    initialize: function () {
      if (initialized) return true;
      discoverApi();
      if (!apiHandle) {
        log("No SCORM API found. Running in preview mode.");
        return false;
      }
      var ok = call("LMSInitialize", "Initialize", "");
      initialized = ok === true || ok === "true";
      if (initialized) {
        setValue("cmi.core.lesson_status", "cmi.completion_status", "incomplete");
        this.commit();
      }
      return initialized;
    },
    commit: function () { return call("LMSCommit", "Commit", ""); },
    finish: function () {
      var ms = new Date() - startTime;
      setValue("cmi.core.session_time", "cmi.session_time", apiVersion === "1.2" ? toScorm12Time(ms) : toScorm2004Time(ms));
      this.commit();
      return call("LMSFinish", "Terminate", "");
    },
    setScore: function (score, min, max) {
      min = min == null ? 0 : min;
      max = max == null ? 100 : max;
      setValue("cmi.core.score.min", "cmi.score.min", min);
      setValue("cmi.core.score.max", "cmi.score.max", max);
      setValue("cmi.core.score.raw", "cmi.score.raw", score);
      if (apiVersion === "2004") setValue("cmi.core.score.raw", "cmi.score.scaled", Math.max(0, Math.min(1, Number(score) / Number(max))));
      return this.commit();
    },
    markComplete: function (passed) {
      if (apiVersion === "1.2") {
        setValue("cmi.core.lesson_status", "cmi.completion_status", passed === false ? "completed" : "passed");
      } else {
        setValue("cmi.core.lesson_status", "cmi.completion_status", "completed");
        setValue("cmi.core.lesson_status", "cmi.success_status", passed === false ? "failed" : "passed");
      }
      return this.commit();
    },
    setLocation: function (location) {
      setValue("cmi.core.lesson_location", "cmi.location", location || "");
      return this.commit();
    },
    getLocation: function () {
      return getValue("cmi.core.lesson_location", "cmi.location");
    },
    setSuspendData: function (data) {
      var serialized = typeof data === "string" ? data : JSON.stringify(data || {});
      setValue("cmi.suspend_data", "cmi.suspend_data", serialized.substring(0, apiVersion === "1.2" ? 4096 : 64000));
      return this.commit();
    },
    getSuspendData: function () {
      var raw = getValue("cmi.suspend_data", "cmi.suspend_data");
      try { return raw ? JSON.parse(raw) : {}; } catch (e) { return raw || ""; }
    },
    recordInteraction: function (id, type, learnerResponse, result, description) {
      var api = discoverApi();
      if (!api) return false;
      var countKey = apiVersion === "1.2" ? "cmi.interactions._count" : "cmi.interactions._count";
      var index = parseInt(getValue(countKey, countKey), 10);
      if (isNaN(index)) index = 0;
      if (apiVersion === "1.2") {
        setValue("cmi.interactions." + index + ".id", "cmi.interactions." + index + ".id", id);
        setValue("cmi.interactions." + index + ".type", "cmi.interactions." + index + ".type", type || "choice");
        setValue("cmi.interactions." + index + ".student_response", "cmi.interactions." + index + ".learner_response", learnerResponse || "");
        setValue("cmi.interactions." + index + ".result", "cmi.interactions." + index + ".result", result || "neutral");
      } else {
        setValue("cmi.interactions." + index + ".id", "cmi.interactions." + index + ".id", id);
        setValue("cmi.interactions." + index + ".type", "cmi.interactions." + index + ".type", type || "choice");
        setValue("cmi.interactions." + index + ".learner_response", "cmi.interactions." + index + ".learner_response", learnerResponse || "");
        setValue("cmi.interactions." + index + ".result", "cmi.interactions." + index + ".result", result || "neutral");
        if (description) setValue("cmi.interactions." + index + ".description", "cmi.interactions." + index + ".description", description);
      }
      return this.commit();
    }
  };

  window.addEventListener("load", function () { window.CourseScorm.initialize(); });
  window.addEventListener("beforeunload", function () { window.CourseScorm.finish(); });
})();
